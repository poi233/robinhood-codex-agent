import unittest
from unittest import mock
import tempfile
from pathlib import Path
import os

from trading_agent.core.context import build_runtime_paths
from trading_agent.core.io import read_json, write_json
from trading_agent.orchestration.premarket import PremarketPipeline
from trading_agent.orchestration import premarket as premarket_module


def _prepare_repo_root(root: Path) -> None:
    (root / "src" / "config").mkdir(parents=True, exist_ok=True)
    (root / "src" / "trading_agent").mkdir(parents=True, exist_ok=True)
    (root / "src" / "config" / "runtime.env").write_text("", encoding="utf-8")


class PremarketOrchestrationTests(unittest.TestCase):
    def test_pipeline_runs_account_snapshot_before_market_context_and_parallel_analyzers(self) -> None:
        events: list[str] = []

        pipeline = PremarketPipeline(
            run_account_snapshot=lambda: events.append("account_snapshot"),
            run_capital_snapshot=lambda: events.append("capital_snapshot"),
            collect_market_context=lambda: events.append("market_context"),
            run_dsa=lambda: events.append("dsa"),
            run_kronos=lambda: events.append("kronos"),
            run_technical=lambda: events.append("technical"),
            run_market_calendar=lambda: events.append("market_calendar"),
            run_quote_snapshot_core=lambda: events.append("quote_snapshot_core"),
            run_trader_watch_levels=lambda: events.append("trader_watch_levels"),
            run_candidate_merge=lambda: events.append("candidate_merge"),
            run_quote_snapshot_candidates=lambda: events.append("quote_snapshot_candidates"),
            run_tradability_candidates=lambda: events.append("tradability_candidates"),
            run_catalyst_enrichment=lambda: events.append("catalyst_enrichment"),
            run_data_status_summary=lambda: events.append("data_status_summary"),
            run_candidate_scoring=lambda: events.append("candidate_scoring"),
            run_risk_overlay=lambda: events.append("risk_overlay"),
            run_final_planner=lambda: events.append("final_planner"),
            run_archive=lambda: events.append("archive"),
        )

        pipeline.run()

        self.assertEqual(events[:3], ["account_snapshot", "capital_snapshot", "market_context"])
        self.assertLess(events.index("account_snapshot"), events.index("quote_snapshot_core"))
        self.assertLess(events.index("technical"), events.index("trader_watch_levels"))
        self.assertLess(events.index("trader_watch_levels"), events.index("candidate_merge"))
        self.assertLess(events.index("candidate_merge"), events.index("quote_snapshot_candidates"))
        self.assertLess(events.index("candidate_merge"), events.index("tradability_candidates"))
        self.assertLess(events.index("candidate_merge"), events.index("catalyst_enrichment"))
        self.assertLess(events.index("quote_snapshot_candidates"), events.index("tradability_candidates"))
        self.assertLess(events.index("quote_snapshot_candidates"), events.index("data_status_summary"))
        self.assertLess(events.index("tradability_candidates"), events.index("data_status_summary"))
        self.assertLess(events.index("catalyst_enrichment"), events.index("data_status_summary"))
        self.assertLess(events.index("data_status_summary"), events.index("candidate_scoring"))
        self.assertLess(events.index("candidate_scoring"), events.index("risk_overlay"))
        self.assertLess(events.index("risk_overlay"), events.index("final_planner"))
        self.assertEqual(events[-2:], ["final_planner", "archive"])

    def test_pipeline_continues_when_advisory_task_fails(self) -> None:
        events: list[str] = []

        def broken_dsa() -> None:
            events.append("dsa")
            raise RuntimeError("boom")

        pipeline = PremarketPipeline(
            run_account_snapshot=lambda: events.append("account_snapshot"),
            run_capital_snapshot=lambda: events.append("capital_snapshot"),
            collect_market_context=lambda: events.append("market_context"),
            run_dsa=broken_dsa,
            run_kronos=lambda: events.append("kronos"),
            run_technical=lambda: events.append("technical"),
            run_market_calendar=lambda: events.append("market_calendar"),
            run_quote_snapshot_core=lambda: events.append("quote_snapshot_core"),
            run_trader_watch_levels=lambda: events.append("trader_watch_levels"),
            run_candidate_merge=lambda: events.append("candidate_merge"),
            run_quote_snapshot_candidates=lambda: events.append("quote_snapshot_candidates"),
            run_tradability_candidates=lambda: events.append("tradability_candidates"),
            run_catalyst_enrichment=lambda: events.append("catalyst_enrichment"),
            run_data_status_summary=lambda: events.append("data_status_summary"),
            run_candidate_scoring=lambda: events.append("candidate_scoring"),
            run_risk_overlay=lambda: events.append("risk_overlay"),
            run_final_planner=lambda: events.append("final_planner"),
            run_archive=lambda: events.append("archive"),
        )

        pipeline.run()
        self.assertIn("final_planner", events)
        self.assertIn("archive", events)

    def test_pipeline_runs_archive_even_when_planner_fails(self) -> None:
        events: list[str] = []

        pipeline = PremarketPipeline(
            run_account_snapshot=lambda: events.append("account_snapshot"),
            run_capital_snapshot=lambda: events.append("capital_snapshot"),
            collect_market_context=lambda: events.append("market_context"),
            run_dsa=lambda: events.append("dsa"),
            run_kronos=lambda: events.append("kronos"),
            run_technical=lambda: events.append("technical"),
            run_market_calendar=lambda: events.append("market_calendar"),
            run_quote_snapshot_core=lambda: events.append("quote_snapshot_core"),
            run_trader_watch_levels=lambda: events.append("trader_watch_levels"),
            run_candidate_merge=lambda: events.append("candidate_merge"),
            run_quote_snapshot_candidates=lambda: events.append("quote_snapshot_candidates"),
            run_tradability_candidates=lambda: events.append("tradability_candidates"),
            run_catalyst_enrichment=lambda: events.append("catalyst_enrichment"),
            run_data_status_summary=lambda: events.append("data_status_summary"),
            run_candidate_scoring=lambda: events.append("candidate_scoring"),
            run_risk_overlay=lambda: events.append("risk_overlay"),
            run_final_planner=lambda: (_ for _ in ()).throw(RuntimeError("planner failed")),
            run_archive=lambda: events.append("archive"),
        )

        with self.assertRaises(RuntimeError):
            pipeline.run()
        self.assertIn("archive", events)

    def test_real_codex_dry_run_env_does_not_force_mock_market_feed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")

            with mock.patch.object(premarket_module, "_is_weekday_pt", return_value=True), \
                mock.patch.object(premarket_module, "collect_market_context") as collect_market_context, \
                mock.patch.object(premarket_module, "run_codex_prompt", return_value=0), \
                mock.patch.object(premarket_module, "_write_kronos_signals"):
                original_cwd = os.getcwd()
                os.chdir(root)
                try:
                    with mock.patch.dict(
                        premarket_module.os.environ,
                        {
                            "CODEX_EXEC_DRY_RUN": "1",
                            "ENABLE_DSA_SIGNAL_LAYER": "0",
                            "ENABLE_KRONOS_SIGNAL_LAYER": "0",
                            "ENABLE_TECHNICAL_SIGNAL_LAYER": "0",
                            "ALLOW_WEEKEND_RUN": "1",
                        },
                        clear=False,
                    ):
                        premarket_module.run_premarket_pipeline(dry_run=False)
                finally:
                    os.chdir(original_cwd)

        self.assertEqual(collect_market_context.call_count, 1)
        self.assertFalse(collect_market_context.call_args.kwargs["mock"])
        self.assertEqual(
            collect_market_context.call_args.kwargs["cache_dir"].resolve(),
            (root / "runtime" / "cache" / "ohlcv").resolve(),
        )

    def test_ohlcv_cache_disabled_via_env_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")

            with mock.patch.object(premarket_module, "_is_weekday_pt", return_value=True), \
                mock.patch.object(premarket_module, "collect_market_context") as collect_market_context, \
                mock.patch.object(premarket_module, "run_codex_prompt", return_value=0), \
                mock.patch.object(premarket_module, "_write_kronos_signals"):
                original_cwd = os.getcwd()
                os.chdir(root)
                try:
                    with mock.patch.dict(
                        premarket_module.os.environ,
                        {
                            "ENABLE_OHLCV_CACHE": "0",
                            "ENABLE_DSA_SIGNAL_LAYER": "0",
                            "ENABLE_KRONOS_SIGNAL_LAYER": "0",
                            "ENABLE_TECHNICAL_SIGNAL_LAYER": "0",
                            "ALLOW_WEEKEND_RUN": "1",
                        },
                        clear=False,
                    ):
                        premarket_module.run_premarket_pipeline(dry_run=False)
                finally:
                    os.chdir(original_cwd)

        self.assertIsNone(collect_market_context.call_args.kwargs["cache_dir"])

    def test_candidate_quote_and_tradability_stages_do_not_call_codex_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")

            with mock.patch.object(premarket_module, "_is_weekday_pt", return_value=True), \
                mock.patch.object(premarket_module, "collect_market_context"), \
                mock.patch.object(premarket_module, "run_codex_prompt", return_value=0) as run_codex_prompt, \
                mock.patch.object(premarket_module, "_write_kronos_signals"), \
                mock.patch.object(premarket_module, "send_trade_email_notification") as notify:
                original_cwd = os.getcwd()
                os.chdir(root)
                try:
                    with mock.patch.dict(
                        premarket_module.os.environ,
                        {
                            "ENABLE_DSA_SIGNAL_LAYER": "0",
                            "ENABLE_KRONOS_SIGNAL_LAYER": "0",
                            "ENABLE_TECHNICAL_SIGNAL_LAYER": "0",
                            "ALLOW_WEEKEND_RUN": "1",
                        },
                        clear=False,
                    ):
                        premarket_module.run_premarket_pipeline(dry_run=False)
                finally:
                    os.chdir(original_cwd)

        run_kinds = [call.args[0] for call in run_codex_prompt.call_args_list]
        self.assertNotIn("quote_snapshot_candidates", run_kinds)
        self.assertNotIn("tradability_candidates", run_kinds)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.kwargs["event_tag"], "PREMARKET_DONE")
        run_date = premarket_module.pt_date_string()
        self.assertEqual(
            notify.call_args.kwargs["report_path"].resolve(),
            (root / "runtime" / "state" / "runs" / run_date / "planner" / "daily_plan.zh.md").resolve(),
        )

    def test_explicit_dry_run_uses_mock_market_feed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")

            with mock.patch.object(premarket_module, "_is_weekday_pt", return_value=True), \
                mock.patch.object(premarket_module, "collect_market_context") as collect_market_context, \
                mock.patch.object(premarket_module, "run_codex_prompt", return_value=0), \
                mock.patch.object(premarket_module, "_write_kronos_signals"):
                original_cwd = os.getcwd()
                os.chdir(root)
                try:
                    with mock.patch.dict(
                        premarket_module.os.environ,
                        {
                            "ENABLE_DSA_SIGNAL_LAYER": "0",
                            "ENABLE_KRONOS_SIGNAL_LAYER": "0",
                            "ENABLE_TECHNICAL_SIGNAL_LAYER": "0",
                            "ALLOW_WEEKEND_RUN": "1",
                        },
                        clear=False,
                    ):
                        premarket_module.run_premarket_pipeline(dry_run=True)
                finally:
                    os.chdir(original_cwd)

            manifest_paths = list((root / "runtime" / "state" / "runs").glob("*/run_manifest.json"))
            manifest = read_json(manifest_paths[0]) if manifest_paths else None

        self.assertEqual(collect_market_context.call_count, 1)
        self.assertTrue(collect_market_context.call_args.kwargs["mock"])
        self.assertEqual(len(manifest_paths), 1)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["strategy_id"], "baseline_v1")
        self.assertIn("config_hash", manifest)
        self.assertIn("git_commit", manifest)

    def test_weekend_gate_honors_runtime_env_local_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")
            (root / "src" / "config" / "runtime.env.local").write_text(
                "ALLOW_WEEKEND_RUN=1\n", encoding="utf-8"
            )

            with mock.patch.object(premarket_module, "_is_weekday_pt", return_value=False), \
                mock.patch.object(premarket_module, "collect_market_context") as collect_market_context, \
                mock.patch.object(premarket_module, "run_codex_prompt", return_value=0), \
                mock.patch.object(premarket_module, "_write_kronos_signals"), \
                mock.patch.object(premarket_module, "send_trade_email_notification"):
                original_cwd = os.getcwd()
                os.chdir(root)
                try:
                    with mock.patch.dict(premarket_module.os.environ, {}, clear=False):
                        premarket_module.os.environ.pop("ALLOW_WEEKEND_RUN", None)
                        status = premarket_module.run_premarket_pipeline(dry_run=False)
                finally:
                    os.chdir(original_cwd)

        # The override lives only in runtime.env.local (never exported to the
        # shell), so the pipeline must load it itself before the weekend gate
        # check runs, not just rely on a pre-populated os.environ.
        self.assertEqual(collect_market_context.call_count, 1)
        self.assertNotEqual(status, None)

    def test_weekend_gate_skips_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")

            with mock.patch.object(premarket_module, "_is_weekday_pt", return_value=False), \
                mock.patch.object(premarket_module, "collect_market_context") as collect_market_context:
                original_cwd = os.getcwd()
                os.chdir(root)
                try:
                    with mock.patch.dict(premarket_module.os.environ, {}, clear=False):
                        premarket_module.os.environ.pop("ALLOW_WEEKEND_RUN", None)
                        status = premarket_module.run_premarket_pipeline(dry_run=False)
                finally:
                    os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(collect_market_context.call_count, 0)

    def test_write_kronos_signals_uses_repo_defaults_when_env_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")
            (root / ".vendor" / "kronos").mkdir(parents=True)
            (root / ".venv-kronos" / "bin").mkdir(parents=True)
            (root / ".venv-kronos" / "bin" / "python").write_text("", encoding="utf-8")

            seen: dict[str, str] = {}

            def fake_run(cmd, check, capture_output, text, env):
                seen["project_root"] = env.get("KRONOS_PROJECT_ROOT", "")
                seen["python_bin"] = env.get("KRONOS_PYTHON_BIN", "")
                return mock.Mock(returncode=0, stderr="", stdout="")

            with mock.patch.dict(
                premarket_module.os.environ,
                {"KRONOS_PROJECT_ROOT": "", "KRONOS_PYTHON_BIN": ""},
                clear=False,
            ), mock.patch.object(premarket_module.subprocess, "run", side_effect=fake_run):
                premarket_module._write_kronos_signals(root)

            self.assertEqual(seen["project_root"], str(root / ".vendor" / "kronos"))
            self.assertEqual(seen["python_bin"], str(root / ".venv-kronos" / "bin" / "python"))

    def test_run_premarket_pipeline_writes_diagnostics_after_daily_plan_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")
            run_date = "2026-06-14"
            paths = build_runtime_paths(root, run_date=run_date)
            paths.market_feed_dir.mkdir(parents=True, exist_ok=True)
            write_json(paths.market_feed_dir / "manifest.json", {"data_status": "ok"})

            def fake_prompt(run_kind, agent_root, prompt_file):
                if run_kind == "account_snapshot":
                    write_json(
                        paths.account_snapshot_path,
                        {
                            "date": run_date,
                            "agentic_account_identified": True,
                            "data_status": "ok",
                            "buying_power": 400000,
                        },
                    )
                elif run_kind == "market_calendar":
                    write_json(paths.market_calendar_path, {"date": run_date, "is_trading_day": True})
                elif run_kind == "quote_snapshot_core":
                    write_json(paths.quote_snapshot_core_path, {"date": run_date, "symbols": {"NVDA": {"last_price": 100, "previous_close": 99, "timestamp": "2026-06-14T09:45:00-07:00", "is_fresh": True}}})
                elif run_kind == "technical_research":
                    write_json(
                        paths.technical_signals_path,
                        {
                            "date": run_date,
                            "symbols": {
                                "NVDA": {
                                    "technical_action": "promote",
                                    "long_setup": {
                                        "status": "active",
                                        "trigger_above": 100.5,
                                        "entry_zone": {"low": 99.5, "high": 100.5},
                                        "invalidation_below": 99.0,
                                        "target_1": 103.0,
                                        "target_2": 105.0,
                                        "do_not_chase_above": 102.0,
                                    },
                                }
                            },
                        },
                    )
                elif run_kind == "catalyst_enrichment":
                    write_json(paths.catalyst_snapshot_path, {"date": run_date, "symbols": {"NVDA": {"status": "completed"}}})
                elif run_kind == "final_premarket":
                    write_json(
                        paths.daily_plan_path,
                        {
                            "date": run_date,
                            "market_regime": "no_trade",
                            "allowed_actions": [],
                            "today_watchlist": [],
                            "no_trade_reasons": ["placeholder"],
                        },
                    )
                    write_json(paths.daily_plan_markdown_path, {"note": "ok"})
                    write_json(paths.daily_plan_zh_markdown_path, {"note": "ok"})
                    write_json(paths.dynamic_allowlist_path, {"date": run_date, "symbol_scores": {"NVDA": {"score": 72.0}}})
                    paths.today_allowlist_path.write_text("NVDA\n", encoding="utf-8")
                    write_json(paths.daily_usage_path, {"date": run_date, "used_notional": 0})
                return 0

            def fake_candidate_scores(agent_root, effective_run_date):
                write_json(
                    paths.candidate_scores_path,
                    {
                        "date": run_date,
                        "symbols": {
                            "NVDA": {
                                "score": 72.0,
                                "score_status": "scored",
                                "blocked": False,
                                "warnings": [],
                                "diagnostics": {
                                    "dsa": {"available": True},
                                    "technical": {"available": True},
                                    "kronos": {"available": True},
                                    "quote": {"available": True},
                                    "catalyst": {"available": True, "missing_numeric_score": True},
                                },
                            }
                        },
                    },
                )

            def fake_risk_overlay(agent_root, effective_run_date, *, trading_mode, risk_tier):
                write_json(
                    paths.risk_overlay_path,
                    {
                        "date": run_date,
                        "watchlist_score_threshold": 35.0,
                        "trade_score_threshold": 50.0,
                        "market_regime": "normal",
                        "risk_level": "normal",
                        "risk_multiplier": 1.0,
                        "watchlist_candidates": ["NVDA"],
                        "tradable_candidates": ["NVDA"],
                        "today_watchlist": ["NVDA"],
                        "allowed_actions": ["small_limit_buy"],
                        "no_trade_reasons": [],
                        "symbol_trade_rules": {"NVDA": {"allow_buy": True}},
                    },
                )

            with mock.patch.object(premarket_module, "_is_weekday_pt", return_value=True), \
                mock.patch.object(premarket_module, "collect_market_context"), \
                mock.patch.object(premarket_module, "run_codex_prompt", side_effect=fake_prompt), \
                mock.patch.object(premarket_module, "_write_kronos_signals", side_effect=lambda agent_root: write_json(paths.kronos_signals_path, {"date": run_date, "symbols": {"NVDA": {"score": 50}}})), \
                mock.patch.object(premarket_module, "run_dsa_scan", side_effect=lambda agent_root, prompt_runner: write_json(paths.dsa_signals_path, {"date": run_date, "symbol_signals": {"NVDA": {"dsa_score": 70, "suggested_premarket_use": "promote"}}})), \
                mock.patch.object(premarket_module, "build_candidate_scores_from_paths", side_effect=fake_candidate_scores), \
                mock.patch.object(premarket_module, "build_risk_overlay_from_paths", side_effect=fake_risk_overlay), \
                mock.patch.object(premarket_module, "send_trade_email_notification"):
                original_cwd = os.getcwd()
                os.chdir(root)
                try:
                    with mock.patch.dict(
                        premarket_module.os.environ,
                        {
                            "ALLOW_WEEKEND_RUN": "1",
                            "RISK_TIER": "3",
                            "TRADING_MODE": "paper",
                            "RUN_DATE_PT": run_date,
                        },
                        clear=False,
                    ):
                        status = premarket_module.run_premarket_pipeline(dry_run=False)
                        diagnostics = read_json(paths.premarket_diagnostics_path)
                finally:
                    os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(diagnostics["final_daily_plan_state"]["plan_state"], "trade_ready")
        self.assertEqual(diagnostics["final_risk_overlay_state"]["tradable_candidates"], ["NVDA"])


class PremarketAdvisoryFailureTests(unittest.TestCase):
    def test_advisory_signal_failure_does_not_break_pipeline(self) -> None:
        """L5: an advisory signal layer (here the H2 factor layer) raising must NOT abort premarket —
        the pipeline still completes and the deterministic score/plan tail still runs."""
        events: list[str] = []

        def boom() -> None:
            events.append("price_factors_attempted")
            raise RuntimeError("factor layer blew up")

        names = ["run_account_snapshot", "run_capital_snapshot", "collect_market_context", "run_dsa",
                 "run_kronos", "run_technical", "run_market_calendar", "run_quote_snapshot_core",
                 "run_trader_watch_levels", "run_candidate_merge", "run_quote_snapshot_candidates",
                 "run_tradability_candidates", "run_catalyst_enrichment", "run_data_status_summary",
                 "run_candidate_scoring", "run_risk_overlay", "run_final_planner", "run_archive"]
        kwargs = {n: (lambda n=n: events.append(n)) for n in names}
        kwargs["run_price_factors"] = boom
        kwargs["run_ai_signals"] = lambda: events.append("run_ai_signals")

        pipeline = PremarketPipeline(**kwargs)
        pipeline.run()  # must not raise despite the advisory failure

        self.assertIn("price_factors_attempted", events)        # the failing stage was attempted
        # the deterministic score/plan tail still ran:
        for required in ("run_candidate_scoring", "run_risk_overlay", "run_final_planner", "run_archive"):
            self.assertIn(required, events)
        # a sibling advisory stage after the failing one still ran:
        self.assertIn("run_ai_signals", events)
