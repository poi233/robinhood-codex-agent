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
            run_final_planner=lambda: events.append("final_planner"),
            run_archive=lambda: events.append("archive"),
        )

        pipeline.run()

        self.assertEqual(events[:2], ["account_snapshot", "market_context"])
        self.assertLess(events.index("account_snapshot"), events.index("quote_snapshot_core"))
        self.assertLess(events.index("technical"), events.index("trader_watch_levels"))
        self.assertLess(events.index("trader_watch_levels"), events.index("candidate_merge"))
        self.assertLess(events.index("candidate_merge"), events.index("quote_snapshot_candidates"))
        self.assertLess(events.index("candidate_merge"), events.index("tradability_candidates"))
        self.assertLess(events.index("candidate_merge"), events.index("catalyst_enrichment"))
        self.assertEqual(events[-2:], ["final_planner", "archive"])

    def test_pipeline_continues_when_advisory_task_fails(self) -> None:
        events: list[str] = []

        def broken_dsa() -> None:
            events.append("dsa")
            raise RuntimeError("boom")

        pipeline = PremarketPipeline(
            run_account_snapshot=lambda: events.append("account_snapshot"),
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
