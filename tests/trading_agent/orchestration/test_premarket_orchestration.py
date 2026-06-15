import unittest
from unittest import mock
import tempfile
from pathlib import Path
import os

from trading_agent.orchestration.premarket import PremarketPipeline
from trading_agent.orchestration import premarket as premarket_module


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
            for dirname in ("config", "scripts", "state", "logs", "reports"):
                (root / dirname).mkdir()
            (root / "src" / "config").mkdir(parents=True)
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

    def test_candidate_quote_and_tradability_stages_do_not_call_codex_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "config").mkdir(parents=True)
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
            for dirname in ("config", "scripts", "state", "logs", "reports"):
                (root / dirname).mkdir()
            (root / "src" / "config").mkdir(parents=True)
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

        self.assertEqual(collect_market_context.call_count, 1)
        self.assertTrue(collect_market_context.call_args.kwargs["mock"])
