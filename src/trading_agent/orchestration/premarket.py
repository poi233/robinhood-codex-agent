from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.run_history import append_stage_log, snapshot_stage_artifacts
from trading_agent.core.time import PT, pt_date_string
from trading_agent.data.market_context import collect_market_context
from trading_agent.data.universe import parse_universe
from trading_agent.planner.candidates import build_candidate_snapshot
from trading_agent.planner.risk_overlay import build_capital_snapshot
from trading_agent.prompts.codex import run_codex_prompt
from trading_agent.reporting.premarket import build_fail_closed_daily_plan, build_premarket_archive_payload
from trading_agent.reporting.trader_watch_levels import build_trader_watch_levels
from trading_agent.signals.kronos import (
    build_failed_kronos_payload,
    build_live_kronos_payload,
    build_mock_kronos_payload,
)
from trading_agent.signals.technical_fallback import build_failed_technical_payload


@dataclass
class PremarketPipeline:
    run_account_snapshot: callable
    run_capital_snapshot: callable
    collect_market_context: callable
    run_dsa: callable
    run_kronos: callable
    run_technical: callable
    run_market_calendar: callable
    run_quote_snapshot_core: callable
    run_trader_watch_levels: callable
    run_candidate_merge: callable
    run_quote_snapshot_candidates: callable
    run_tradability_candidates: callable
    run_catalyst_enrichment: callable
    run_final_planner: callable
    run_archive: callable

    def run(self) -> None:
        self.run_account_snapshot()
        self.run_capital_snapshot()
        self.collect_market_context()
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(self._run_advisory, self.run_dsa),
                executor.submit(self._run_advisory, self.run_kronos),
                executor.submit(self._run_advisory, self.run_technical),
                executor.submit(self._run_advisory, self.run_market_calendar),
                executor.submit(self._run_advisory, self.run_quote_snapshot_core),
            ]
            wait(futures)
        self.run_trader_watch_levels()
        self.run_candidate_merge()
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(self._run_advisory, self.run_quote_snapshot_candidates),
                executor.submit(self._run_advisory, self.run_tradability_candidates),
                executor.submit(self._run_advisory, self.run_catalyst_enrichment),
            ]
            wait(futures)
        planner_error: Exception | None = None
        try:
            self.run_final_planner()
        except Exception as exc:
            planner_error = exc
        self.run_archive()
        if planner_error is not None:
            raise planner_error

    @staticmethod
    def _run_advisory(fn: callable) -> None:
        try:
            fn()
        except Exception:
            return


def _is_weekday_pt() -> bool:
    return __import__("datetime").datetime.now(tz=PT).weekday() < 5


def _write_kronos_signals(agent_root: Path) -> None:
    paths = build_runtime_paths(agent_root)
    universe_file = paths.config_dir / "universe.txt"
    output_file = paths.kronos_signals_path
    symbols = parse_universe(universe_file)
    run_date = paths.run_date
    kronos_python = os.environ.get("KRONOS_PYTHON_BIN")
    if kronos_python and Path(kronos_python).exists():
        current_python = Path(sys.executable).resolve()
        requested_python = Path(kronos_python).resolve()
        if requested_python != current_python:
            cmd = [
                kronos_python,
                str(paths.scripts_dir / "kronos" / "kronos_generate_signals.py"),
                "--universe-file",
                str(universe_file),
                "--output-file",
                str(output_file),
                "--date",
                run_date,
            ]
            if os.environ.get("KRONOS_USE_MOCK", "0") == "1":
                cmd.append("--mock")
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                env=os.environ.copy(),
            )
            if result.returncode != 0:
                message = (result.stderr or result.stdout or "external kronos runner failed").strip()
                raise RuntimeError(message)
            return
    payload = (
        build_mock_kronos_payload(symbols, run_date, str(universe_file))
        if os.environ.get("KRONOS_USE_MOCK", "0") == "1"
        else build_live_kronos_payload(symbols, run_date, str(universe_file))
    )
    write_json(output_file, payload)


def run_premarket_pipeline(*, dry_run: bool) -> int:
    agent_root = Path.cwd()
    if not _is_weekday_pt() and os.environ.get("ALLOW_WEEKEND_RUN", "0") != "1":
        return 0

    paths = build_runtime_paths(agent_root)
    run_date = paths.run_date
    market_feed_dir = paths.market_feed_dir
    timeframes = [value.strip() for value in os.environ.get("MARKET_FEED_TIMEFRAMES", "1w,1d,1h,15m").split(",") if value.strip()]
    news_limit = int(os.environ.get("MARKET_FEED_NEWS_LIMIT", "5"))

    def run_stage(stage: str, fn: callable, *, snapshot: bool = True) -> None:
        started = time.perf_counter()
        append_stage_log(agent_root, run_date, stage, "started", f"{stage} started")
        try:
            fn()
            copied = snapshot_stage_artifacts(agent_root, run_date, stage) if snapshot else []
            append_stage_log(
                agent_root,
                run_date,
                stage,
                "completed",
                f"{stage} completed",
                elapsed_seconds=time.perf_counter() - started,
                details={"artifacts": copied},
            )
        except Exception as exc:
            copied = snapshot_stage_artifacts(agent_root, run_date, stage) if snapshot else []
            append_stage_log(
                agent_root,
                run_date,
                stage,
                "failed",
                f"{stage} failed: {exc}",
                elapsed_seconds=time.perf_counter() - started,
                details={"artifacts": copied},
            )
            raise

    def run_account_snapshot() -> None:
        status = run_codex_prompt(
            "account_snapshot",
            agent_root,
            paths.prompts_dir / "premarket" / "account_snapshot.txt",
        )
        if status != 0:
            raise RuntimeError("account snapshot prompt failed")

    def run_capital_snapshot() -> None:
        account_snapshot = read_json(paths.account_snapshot_path) if paths.account_snapshot_path.exists() else {}
        paper_account = read_json(paths.paper_account_path) if paths.paper_account_path.exists() else None
        paper_starting_cash = float(os.environ.get("PAPER_STARTING_CASH", "400000") or 400000)
        write_json(
            paths.capital_snapshot_path,
            build_capital_snapshot(
                run_date=run_date,
                trading_mode=os.environ.get("TRADING_MODE", "paper"),
                paper_account=paper_account if isinstance(paper_account, dict) else None,
                account_snapshot=account_snapshot if isinstance(account_snapshot, dict) else {},
                paper_starting_cash=paper_starting_cash,
            ),
        )

    def collect_context() -> None:
        if os.environ.get("ENABLE_MARKET_FEED_LAYER", "1") != "1":
            append_stage_log(agent_root, run_date, "market_context", "skipped", "market feed layer disabled")
            return
        collect_market_context(
            universe_file=paths.config_dir / "universe.txt",
            output_dir=market_feed_dir,
            run_date=run_date,
            timeframes=timeframes,
            news_limit=news_limit,
            mock=dry_run,
        )

    def run_dsa() -> None:
        if os.environ.get("ENABLE_DSA_SIGNAL_LAYER", "1") != "1":
            append_stage_log(agent_root, run_date, "dsa", "skipped", "DSA signal layer disabled")
            return
        status = run_codex_prompt("dsa_premarket_scan", agent_root, paths.prompts_dir / "signals" / "dsa_scan.txt")
        if status != 0:
            raise RuntimeError("dsa prompt failed")

    def run_kronos() -> None:
        if os.environ.get("ENABLE_KRONOS_SIGNAL_LAYER", "1") != "1":
            append_stage_log(agent_root, run_date, "kronos", "skipped", "Kronos signal layer disabled")
            return
        try:
            _write_kronos_signals(agent_root)
        except Exception as exc:
            payload = build_failed_kronos_payload(
                run_date,
                str(paths.config_dir / "universe.txt"),
                f"live Kronos generation failed: {exc}",
                "inference_only",
            )
            write_json(paths.kronos_signals_path, payload)
            raise

    def run_technical() -> None:
        if os.environ.get("ENABLE_TECHNICAL_SIGNAL_LAYER", "1") != "1":
            append_stage_log(agent_root, run_date, "technical", "skipped", "technical signal layer disabled")
            return
        manifest_path = market_feed_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("market feed manifest missing")
        manifest = read_json(manifest_path)
        if manifest.get("data_status") != "ok":
            write_json(
                paths.technical_signals_path,
                build_failed_technical_payload(
                    manifest,
                    run_date=run_date,
                    reason="market feed was not complete enough for technical analysis; technical layer is fail-closed",
                ),
            )
            return
        status = run_codex_prompt("technical_research", agent_root, paths.prompts_dir / "technical" / "research.txt")
        if status != 0:
            write_json(
                paths.technical_signals_path,
                build_failed_technical_payload(
                    manifest,
                    run_date=run_date,
                    reason="technical research prompt failed; archived conservative price levels for watch-only use",
                ),
            )
            raise RuntimeError("technical prompt failed")

    def run_market_calendar() -> None:
        status = run_codex_prompt(
            "market_calendar",
            agent_root,
            paths.prompts_dir / "premarket" / "market_calendar.txt",
        )
        if status != 0:
            raise RuntimeError("market calendar prompt failed")

    def run_quote_snapshot_core() -> None:
        status = run_codex_prompt(
            "quote_snapshot_core",
            agent_root,
            paths.prompts_dir / "premarket" / "quote_snapshot_core.txt",
        )
        if status != 0:
            raise RuntimeError("quote snapshot core prompt failed")

    def run_candidate_merge() -> None:
        build_candidate_snapshot(agent_root, run_date)

    def run_trader_watch_levels() -> None:
        if not paths.technical_signals_path.exists():
            write_json(paths.trader_watch_levels_path, {"schema_version": 1, "symbols": {}})
            return
        write_json(paths.trader_watch_levels_path, build_trader_watch_levels(read_json(paths.technical_signals_path)))

    def run_quote_snapshot_candidates() -> None:
        status = run_codex_prompt(
            "quote_snapshot_candidates",
            agent_root,
            paths.prompts_dir / "premarket" / "quote_snapshot_candidates.txt",
        )
        if status != 0:
            raise RuntimeError("quote snapshot candidates prompt failed")

    def run_tradability_candidates() -> None:
        status = run_codex_prompt(
            "tradability_candidates",
            agent_root,
            paths.prompts_dir / "premarket" / "tradability_candidates.txt",
        )
        if status != 0:
            raise RuntimeError("tradability candidates prompt failed")

    def run_catalyst_enrichment() -> None:
        status = run_codex_prompt(
            "catalyst_enrichment",
            agent_root,
            paths.prompts_dir / "premarket" / "catalyst_enrichment.txt",
        )
        if status != 0:
            raise RuntimeError("catalyst enrichment prompt failed")

    def run_final_planner() -> None:
        status = run_codex_prompt("final_premarket", agent_root, paths.prompts_dir / "premarket" / "final_research.txt")
        if status != 0:
            raise RuntimeError("premarket prompt failed")

    def run_archive() -> None:
        technical_path = paths.technical_signals_path
        if not technical_path.exists():
            return
        daily_plan_path = paths.daily_plan_path
        daily_plan = (
            read_json(daily_plan_path)
            if daily_plan_path.exists()
            else build_fail_closed_daily_plan(
                run_date,
                "premarket planner output missing; archived technical layer only",
            )
        )
        payload = build_premarket_archive_payload(
            run_date=run_date,
            daily_plan=daily_plan,
            technical_payload=read_json(technical_path),
        )
        archive_output = paths.archive_dir / "premarket_report.json"
        archive_output.parent.mkdir(parents=True, exist_ok=True)
        write_json(archive_output, payload)

    pipeline = PremarketPipeline(
        run_account_snapshot=lambda: run_stage("account_snapshot", run_account_snapshot),
        run_capital_snapshot=lambda: run_stage("capital_snapshot", run_capital_snapshot),
        collect_market_context=lambda: run_stage("market_context", collect_context),
        run_dsa=lambda: run_stage("dsa", run_dsa),
        run_kronos=lambda: run_stage("kronos", run_kronos),
        run_technical=lambda: run_stage("technical", run_technical),
        run_market_calendar=lambda: run_stage("market_calendar", run_market_calendar),
        run_quote_snapshot_core=lambda: run_stage("quote_snapshot_core", run_quote_snapshot_core),
        run_trader_watch_levels=lambda: run_stage("trader_watch_levels", run_trader_watch_levels),
        run_candidate_merge=lambda: run_stage("candidate_merge", run_candidate_merge),
        run_quote_snapshot_candidates=lambda: run_stage("quote_snapshot_candidates", run_quote_snapshot_candidates),
        run_tradability_candidates=lambda: run_stage("tradability_candidates", run_tradability_candidates),
        run_catalyst_enrichment=lambda: run_stage("catalyst_enrichment", run_catalyst_enrichment),
        run_final_planner=lambda: run_stage("final_planner", run_final_planner),
        run_archive=lambda: run_stage("archive", run_archive),
    )
    append_stage_log(agent_root, run_date, "pipeline", "started", "premarket pipeline started")
    try:
        pipeline.run()
    except Exception as exc:
        append_stage_log(agent_root, run_date, "pipeline", "failed", f"premarket pipeline failed: {exc}")
        raise
    append_stage_log(agent_root, run_date, "pipeline", "completed", "premarket pipeline completed")
    return 0
