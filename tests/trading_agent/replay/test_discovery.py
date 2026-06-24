import unittest
from pathlib import Path
from unittest import mock

from trading_agent.replay import discovery
from trading_agent.replay.discovery import (
    _forward_return_index,
    blocked_reason_edge,
    build_discovery_report,
    top_blocked_winners,
)
from trading_agent.replay.forward_returns import ForwardReturnRecord


def _rec(run_date: str, symbol: str, ret: float | None) -> ForwardReturnRecord:
    return ForwardReturnRecord(
        run_date=run_date, symbol=symbol, candidate_score=None,
        trade_readiness_score=None, price_setup_score=None, returns={5: ret},
    )


class ForwardIndexTests(unittest.TestCase):
    def test_index_keys_and_skips_none(self):
        idx = _forward_return_index([_rec("2026-06-10", "AAA", 0.05), _rec("2026-06-10", "BBB", None)], 5)
        self.assertEqual(idx, {("2026-06-10", "AAA"): 0.05})


class BlockedReasonEdgeTests(unittest.TestCase):
    def test_ranks_reasons_by_forward_return(self):
        decisions = [
            {"_run_date": "2026-06-10", "per_candidate_blocks": {"AAA": ["no_trade_zone"], "BBB": ["stale_quote"]}},
            {"_run_date": "2026-06-11", "per_candidate_blocks": {"CCC": ["no_trade_zone"]}},
        ]
        fwd = {("2026-06-10", "AAA"): 0.08, ("2026-06-10", "BBB"): -0.02, ("2026-06-11", "CCC"): 0.04}
        with mock.patch.object(discovery, "collect_decisions", return_value=decisions):
            rows = blocked_reason_edge(Path("/x"), run_dates=["2026-06-10", "2026-06-11"], fwd_index=fwd)
        by_reason = {r["reason"]: r for r in rows}
        self.assertEqual(by_reason["no_trade_zone"]["blocked_with_known_return"], 2)
        self.assertEqual(by_reason["no_trade_zone"]["mean_fwd_return"], 0.06)  # (0.08 + 0.04)/2
        self.assertEqual(by_reason["no_trade_zone"]["win_rate"], 1.0)
        self.assertEqual(by_reason["stale_quote"]["mean_fwd_return"], -0.02)
        self.assertEqual(rows[0]["reason"], "no_trade_zone")  # highest mean sorts first

    def test_skips_candidates_without_forward_return(self):
        decisions = [{"_run_date": "2026-06-10", "per_candidate_blocks": {"AAA": ["x"]}}]
        with mock.patch.object(discovery, "collect_decisions", return_value=decisions):
            rows = blocked_reason_edge(Path("/x"), run_dates=["2026-06-10"], fwd_index={})
        self.assertEqual(rows, [])


class TopBlockedWinnersTests(unittest.TestCase):
    def test_sorted_desc_and_capped(self):
        decisions = [{"_run_date": "2026-06-10", "per_candidate_blocks": {"AAA": ["no_trade_zone"], "BBB": ["x"]}}]
        fwd = {("2026-06-10", "AAA"): 0.08, ("2026-06-10", "BBB"): 0.20}
        with mock.patch.object(discovery, "collect_decisions", return_value=decisions):
            rows = top_blocked_winners(Path("/x"), run_dates=["2026-06-10"], fwd_index=fwd, top_k=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "BBB")
        self.assertEqual(rows[0]["fwd_return"], 0.2)


class BuildReportTests(unittest.TestCase):
    def test_no_data(self):
        with mock.patch.object(discovery, "discover_run_dates", return_value=[]):
            report = build_discovery_report(Path("/x"))
        self.assertEqual(report["status"], "no_data")

    def test_end_to_end_with_mocks(self):
        decisions = [{"_run_date": "2026-06-10", "per_candidate_blocks": {"AAA": ["no_trade_zone"]}}]
        with mock.patch.object(discovery, "discover_run_dates", return_value=["2026-06-10"]), \
            mock.patch.object(discovery, "compute_forward_return_records", return_value=[_rec("2026-06-10", "AAA", 0.08)]), \
            mock.patch.object(discovery, "collect_decisions", return_value=decisions), \
            mock.patch.object(discovery, "load_trade_thresholds", return_value={"2026-06-10": 50.0}):
            report = build_discovery_report(Path("/x"), lookahead=5)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["blocked_reason_edge"][0]["reason"], "no_trade_zone")
        self.assertEqual(report["top_blocked_winners"][0]["symbol"], "AAA")


if __name__ == "__main__":
    unittest.main()
