import unittest
from unittest import mock
import tempfile
from pathlib import Path
import os

from trading_agent.orchestration.premarket import PremarketPipeline
from trading_agent.orchestration import premarket as premarket_module


class PremarketOrchestrationTests(unittest.TestCase):
    def test_pipeline_runs_market_context_before_parallel_analyzers(self) -> None:
        events: list[str] = []

        pipeline = PremarketPipeline(
            collect_market_context=lambda: events.append("market_context"),
            run_dsa=lambda: events.append("dsa"),
            run_kronos=lambda: events.append("kronos"),
            run_technical=lambda: events.append("technical"),
            run_planner=lambda: events.append("planner"),
            run_archive=lambda: events.append("archive"),
        )

        pipeline.run()

        self.assertEqual(events[0], "market_context")
        self.assertEqual(events[-2:], ["planner", "archive"])

    def test_pipeline_continues_when_advisory_task_fails(self) -> None:
        events: list[str] = []

        def broken_dsa() -> None:
            events.append("dsa")
            raise RuntimeError("boom")

        pipeline = PremarketPipeline(
            collect_market_context=lambda: events.append("market_context"),
            run_dsa=broken_dsa,
            run_kronos=lambda: events.append("kronos"),
            run_technical=lambda: events.append("technical"),
            run_planner=lambda: events.append("planner"),
            run_archive=lambda: events.append("archive"),
        )

        pipeline.run()
        self.assertIn("planner", events)
        self.assertIn("archive", events)

    def test_pipeline_runs_archive_even_when_planner_fails(self) -> None:
        events: list[str] = []

        pipeline = PremarketPipeline(
            collect_market_context=lambda: events.append("market_context"),
            run_dsa=lambda: events.append("dsa"),
            run_kronos=lambda: events.append("kronos"),
            run_technical=lambda: events.append("technical"),
            run_planner=lambda: (_ for _ in ()).throw(RuntimeError("planner failed")),
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
            (root / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")

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
            (root / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")

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
