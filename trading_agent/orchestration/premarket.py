from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.core.time import PT, pt_date_string
from trading_agent.data.market_context import collect_market_context
from trading_agent.data.universe import parse_universe
from trading_agent.prompts.codex import run_codex_prompt
from trading_agent.reporting.archive import write_premarket_archive_json
from trading_agent.reporting.premarket import build_fail_closed_daily_plan, build_premarket_archive_payload
from trading_agent.signals.kronos import (
    build_failed_kronos_payload,
    build_live_kronos_payload,
    build_mock_kronos_payload,
)
from trading_agent.signals.technical_fallback import build_failed_technical_payload


@dataclass
class PremarketPipeline:
    collect_market_context: callable
    run_dsa: callable
    run_kronos: callable
    run_technical: callable
    run_planner: callable
    run_archive: callable

    def run(self) -> None:
        self.collect_market_context()
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(self._run_advisory, self.run_dsa),
                executor.submit(self._run_advisory, self.run_kronos),
                executor.submit(self._run_advisory, self.run_technical),
            ]
            wait(futures)
        planner_error: Exception | None = None
        try:
            self.run_planner()
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
    universe_file = agent_root / "config" / "universe.txt"
    output_file = agent_root / "state" / "kronos_signals.json"
    symbols = parse_universe(universe_file)
    run_date = pt_date_string()
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
    market_feed_dir = Path(os.environ.get("MARKET_FEED_DIR", str(paths.state_dir / "market_feed" / pt_date_string())))
    timeframes = [value.strip() for value in os.environ.get("MARKET_FEED_TIMEFRAMES", "1w,1d,1h,15m").split(",") if value.strip()]
    news_limit = int(os.environ.get("MARKET_FEED_NEWS_LIMIT", "5"))

    def collect_context() -> None:
        if os.environ.get("ENABLE_MARKET_FEED_LAYER", "1") != "1":
            return
        collect_market_context(
            universe_file=paths.config_dir / "universe.txt",
            output_dir=market_feed_dir,
            run_date=pt_date_string(),
            timeframes=timeframes,
            news_limit=news_limit,
            mock=dry_run,
        )

    def run_dsa() -> None:
        if os.environ.get("ENABLE_DSA_SIGNAL_LAYER", "1") != "1":
            return
        status = run_codex_prompt("dsa_premarket_scan", agent_root, agent_root / "prompts" / "dsa_premarket_scan.txt")
        if status != 0:
            raise RuntimeError("dsa prompt failed")

    def run_kronos() -> None:
        if os.environ.get("ENABLE_KRONOS_SIGNAL_LAYER", "1") != "1":
            return
        try:
            _write_kronos_signals(agent_root)
        except Exception as exc:
            payload = build_failed_kronos_payload(
                pt_date_string(),
                str(paths.config_dir / "universe.txt"),
                f"live Kronos generation failed: {exc}",
                "inference_only",
            )
            write_json(paths.state_dir / "kronos_signals.json", payload)
            raise

    def run_technical() -> None:
        if os.environ.get("ENABLE_TECHNICAL_SIGNAL_LAYER", "1") != "1":
            return
        manifest_path = market_feed_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("market feed manifest missing")
        manifest = read_json(manifest_path)
        if manifest.get("data_status") != "ok":
            write_json(
                paths.state_dir / "technical_signals.json",
                build_failed_technical_payload(
                    manifest,
                    run_date=pt_date_string(),
                    reason="market feed was not complete enough for technical analysis; technical layer is fail-closed",
                ),
            )
            return
        status = run_codex_prompt("technical_research", agent_root, agent_root / "prompts" / "technical_research.txt")
        if status != 0:
            write_json(
                paths.state_dir / "technical_signals.json",
                build_failed_technical_payload(
                    manifest,
                    run_date=pt_date_string(),
                    reason="technical research prompt failed; archived conservative price levels for watch-only use",
                ),
            )
            raise RuntimeError("technical prompt failed")

    def run_planner() -> None:
        status = run_codex_prompt("premarket", agent_root, agent_root / "prompts" / "premarket_research.txt")
        if status != 0:
            raise RuntimeError("premarket prompt failed")

    def run_archive() -> None:
        technical_path = paths.state_dir / "technical_signals.json"
        if not technical_path.exists():
            return
        daily_plan_path = paths.state_dir / "daily_plan.json"
        daily_plan = (
            read_json(daily_plan_path)
            if daily_plan_path.exists()
            else build_fail_closed_daily_plan(
                pt_date_string(),
                "premarket planner output missing; archived technical layer only",
            )
        )
        payload = build_premarket_archive_payload(
            run_date=pt_date_string(),
            daily_plan=daily_plan,
            technical_payload=read_json(technical_path),
        )
        write_premarket_archive_json(paths.reports_dir, pt_date_string(), payload)

    pipeline = PremarketPipeline(
        collect_market_context=collect_context,
        run_dsa=run_dsa,
        run_kronos=run_kronos,
        run_technical=run_technical,
        run_planner=run_planner,
        run_archive=run_archive,
    )
    pipeline.run()
    return 0
