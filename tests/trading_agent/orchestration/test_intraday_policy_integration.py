import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from trading_agent.core.config import TierMisconfigurationError
from trading_agent.core.time import PT
from trading_agent.orchestration import intraday as intraday_module
from trading_agent.paper.broker import apply_paper_intent
from trading_agent.policy.advisory_overlay import AdvisoryOverlay, SymbolOverlay
from trading_agent.policy.models import OrderIntent, PolicyDecision, PolicyInputs, Quote


def policy_ready_inputs(*, trading_mode: str = "paper") -> PolicyInputs:
    fresh_timestamp = datetime.now(tz=PT).isoformat()
    return PolicyInputs(
        run_date="2026-06-14",
        trading_mode=trading_mode,
        risk_tier=0,
        risk_caps={"max_single_order_notional": 10, "max_daily_notional": 25},
        universe=["NVDA"],
        today_allowlist=["NVDA"],
        daily_plan={
            "date": "2026-06-14",
            "market_regime": "normal",
            "allowed_actions": ["small_limit_buy"],
            "today_watchlist": ["NVDA"],
            "symbol_trade_rules": {"NVDA": {"max_notional": 10}},
        },
        dynamic_allowlist={"date": "2026-06-14", "symbol_scores": {"NVDA": {"score": 85}}},
        candidate_scores={"date": "2026-06-14", "symbols": {"NVDA": {"score": 85, "total_score": 85, "components": {"technical": 78, "catalyst": 70}}}},
        risk_overlay={
            "date": "2026-06-14",
            "market_regime": "aggressive_ok",
            "max_single_order_notional": 10,
            "max_daily_notional": 25,
            "symbol_trade_rules": {"NVDA": {"max_notional": 10, "allow_buy": True}},
        },
        trader_watch_levels={
            "symbols": {
                "NVDA": {
                    "entry_low": 99.5,
                    "entry_high": 100.5,
                    "buy_trigger_above": 100.5,
                    "do_not_chase_above": 102.0,
                    "no_trade_low": 100.6,
                    "no_trade_high": 100.9,
                    "invalidation_below": 99.0,
                    "risk_reduction_trigger_below": 98.5,
                    "risk_reduction_target_1": 97.5,
                    "risk_reduction_target_2": 96.0,
                    "target_1": 103.0,
                    "target_2": 105.0,
                }
            }
        },
        data_status_summary={"execution_blocking": False, "reason_codes": []},
        capital_snapshot={"sizing_buying_power": 25.0},
        catalyst_snapshot={"symbols": {"NVDA": {"score": 70}}},
        policy_profile={
            "name": "aggressive_growth",
            "per_trade_risk_pct": 0.005,
            "cash_buffer_pct": 0.1,
            "pullback_score_threshold": 82,
            "breakout_score_threshold": 88,
            "technical_min_score": 70,
            "min_reward_risk": 1.5,
            "breakout_chase_tolerance_pct": 0.002,
            "minimum_trade_notional": 1.0,
        },
        daily_usage={"date": "2026-06-14", "used_notional": 0},
        account={"buying_power": 25.0},
        quotes={"NVDA": Quote(symbol="NVDA", price=100.0, previous_close=101.0, timestamp=fresh_timestamp)},
        technical_signals={
            "symbols": {
                "NVDA": {
                    "long_setup": {
                        "status": "active",
                        "trigger_above": 100.5,
                        "entry_zone": {"low": 99.5, "high": 100.5},
                        "invalidation_below": 99.0,
                        "target_1": 103.0,
                        "target_2": 105.0,
                        "do_not_chase_above": 102.0,
                    },
                    "short_setup": {
                        "status": "watch",
                        "trigger_below": 98.5,
                        "target_1": 97.5,
                        "target_2": 96.0,
                    },
                    "no_trade_zone": {"low": 100.6, "high": 100.9, "reason": "range chop"},
                }
            }
        },
    )


def policy_ready_inputs_with_overlay() -> PolicyInputs:
    inputs = policy_ready_inputs()
    inputs.advisory_overlay = AdvisoryOverlay(
        run_date="2026-06-14",
        symbols={
            "NVDA": SymbolOverlay(
                symbol="NVDA",
                rank_delta=0.0,
                size_multiplier=1.0,
                block_buy=False,
                reason_codes=["factor_alpha", "ai", "regime", "portfolio"],
                components={
                    "factor_alpha": {"score": 84.0},
                    "ai": {"kronos": {"direction": "long", "confidence": 0.8}},
                    "regime": {"regime": "neutral", "applied_multiplier": 1.0},
                    "portfolio": {"position_weight": 0.04},
                },
            )
        },
    )
    return inputs


def policy_ready_inputs_with_overlay_block() -> PolicyInputs:
    inputs = policy_ready_inputs()
    inputs.advisory_overlay = AdvisoryOverlay(
        run_date="2026-06-14",
        symbols={
            "NVDA": SymbolOverlay(
                symbol="NVDA",
                block_buy=True,
                blocked_reasons=["regime_blocks_new_buy"],
                size_multiplier=0.0,
                components={"regime": {"regime": "risk_off", "applied_multiplier": 0.0}},
            )
        },
    )
    return inputs


def read_decisions(root: Path) -> list[dict[str, object]]:
    path = root / "runtime" / "logs" / "runs" / "2026-06-14" / "audit" / "decisions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _prepare_repo_root(root: Path) -> None:
    (root / "src" / "config").mkdir(parents=True, exist_ok=True)
    (root / "src" / "trading_agent").mkdir(parents=True, exist_ok=True)
    (root / "src" / "config" / "runtime.env").write_text("", encoding="utf-8")


class IntradayPolicyIntegrationTests(unittest.TestCase):
    def test_weekend_gate_honors_runtime_env_local_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "runtime.env.local").write_text(
                "ALLOW_WEEKEND_RUN=1\n", encoding="utf-8"
            )
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=False), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs()), \
                    mock.patch.object(intraday_module, "run_codex_prompt"), \
                    mock.patch.object(intraday_module, "send_trade_email_notification"):
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)
                    with mock.patch.dict(intraday_module.os.environ, {}, clear=False):
                        intraday_module.os.environ.pop("ALLOW_WEEKEND_RUN", None)
                        status = intraday_module.run_intraday_pipeline(dry_run=False)
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        # ALLOW_WEEKEND_RUN only exists in runtime.env.local here, never in
        # os.environ directly, so passing the gate proves load_env_files ran
        # before the weekend check.
        self.assertEqual(status, 0)
        self.assertEqual(decisions[0]["decision"], "would_trade")

    def test_weekend_gate_skips_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=False), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"):
                    with mock.patch.dict(intraday_module.os.environ, {}, clear=False):
                        intraday_module.os.environ.pop("ALLOW_WEEKEND_RUN", None)
                        status = intraday_module.run_intraday_pipeline(dry_run=False)
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(decisions[0]["decision"], "calendar_skip")

    def test_intraday_fails_closed_when_live_mode_has_tier_4(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.dict(
                        intraday_module.os.environ,
                        {"TRADING_MODE": "live", "RISK_TIER": "4"},
                        clear=False,
                    ):
                    with self.assertRaises(TierMisconfigurationError):
                        intraday_module.run_intraday_pipeline(dry_run=False)
            finally:
                os.chdir(original_cwd)

    def test_intraday_uses_policy_and_does_not_call_codex_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs()), \
                    mock.patch.object(intraday_module, "run_codex_prompt") as run_codex_prompt, \
                    mock.patch.object(intraday_module, "send_trade_email_notification") as notify:
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)

                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    decisions = read_decisions(root)
                    paper_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "paper"
                    paper_orders_written = (paper_dir / "orders.jsonl").exists()
                    day_start_written = (paper_dir / "day_start.json").exists()
                    equity_curve_written = (paper_dir / "equity_curve.jsonl").exists()
                    manifest_path = root / "runtime" / "state" / "runs" / "2026-06-14" / "run_manifest.json"
                    manifest_written = manifest_path.exists()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        run_codex_prompt.assert_not_called()
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["decision"], "would_trade")
        self.assertEqual(decisions[0]["action_taken"], "paper_fill")
        self.assertEqual(decisions[0]["proposed_order"]["symbol"], "NVDA")
        self.assertTrue(paper_orders_written)
        self.assertTrue(day_start_written)
        self.assertTrue(equity_curve_written)
        self.assertTrue(manifest_written)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.kwargs["event_tag"], "TRADE_EXECUTED")
        self.assertIn("【买入原因】", notify.call_args.kwargs["body"])
        self.assertIn("模拟盘已买入 NVDA", notify.call_args.kwargs["body"])

    def test_intraday_persists_ranking_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs()), \
                    mock.patch.object(intraday_module, "send_trade_email_notification"):
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)

                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    rankings_path = root / "runtime" / "logs" / "runs" / "2026-06-14" / "audit" / "intraday_rankings.jsonl"
                    rankings = [json.loads(line) for line in rankings_path.read_text(encoding="utf-8").splitlines()]
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(len(rankings), 1)
        self.assertEqual(rankings[0]["symbol"], "NVDA")
        # The two scores that were never persisted before: both present and numeric.
        self.assertIn("trade_readiness_score", rankings[0])
        self.assertIn("price_setup_score", rankings[0])
        self.assertGreater(rankings[0]["price_setup_score"], 0)

    def test_intraday_persists_advisory_overlay_audit_without_changing_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs_with_overlay()), \
                    mock.patch.object(intraday_module, "send_trade_email_notification"):
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)

                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    rankings_path = root / "runtime" / "logs" / "runs" / "2026-06-14" / "audit" / "intraday_rankings.jsonl"
                    rankings = [json.loads(line) for line in rankings_path.read_text(encoding="utf-8").splitlines()]
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(rankings[0]["trade_readiness_score"], 81.75)
        self.assertEqual(rankings[0]["advisory_overlay"]["rank_delta"], 0.0)
        self.assertEqual(rankings[0]["advisory_overlay"]["components"]["factor_alpha"]["score"], 84.0)
        proposed_order = decisions[0]["proposed_order"]
        self.assertEqual(proposed_order["advisory_overlay"]["size_multiplier"], 1.0)
        self.assertEqual(proposed_order["advisory_overlay"]["components"]["ai"]["kronos"]["direction"], "long")

    def test_intraday_persists_advisory_overlay_for_blocked_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs_with_overlay_block()):
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)

                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    rankings_path = root / "runtime" / "logs" / "runs" / "2026-06-14" / "audit" / "intraday_rankings.jsonl"
                    rankings = [json.loads(line) for line in rankings_path.read_text(encoding="utf-8").splitlines()]
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(decisions[0]["decision"], "blocked")
        self.assertIn("regime_blocks_new_buy", decisions[0]["blocked_reasons"])
        self.assertEqual(rankings[0]["symbol"], "NVDA")
        self.assertEqual(rankings[0]["blocked_reasons"], ["regime_blocks_new_buy"])
        self.assertTrue(rankings[0]["advisory_overlay"]["block_buy"])
        self.assertEqual(rankings[0]["advisory_overlay"]["components"]["regime"]["regime"], "risk_off")

    def test_intraday_runs_active_shadow_experiment_in_isolated_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "src" / "config" / "strategy_experiments.yaml").write_text(
                "experiments:\n"
                "  exp_2026-06-14_scoring_trade_threshold:\n"
                "    status: active_shadow\n"
                "    challenger_strategy_id: \"baseline_v1__trade_threshold_40\"\n"
                "    module: scoring\n"
                "    field: trade_threshold\n"
                "    current: 50.0\n"
                "    proposed: 40.0\n",
                encoding="utf-8",
            )
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs()), \
                    mock.patch.object(intraday_module, "send_trade_email_notification"):
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)
                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    shadow_log = root / "runtime" / "state" / "runs" / "2026-06-14" / "experiments" / "baseline_v1__trade_threshold_40" / "shadow_decisions.jsonl"
                    shadow_written = shadow_log.exists()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertTrue(shadow_written)

    def test_intraday_requires_live_quotes_in_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs()) as load_policy_inputs, \
                    mock.patch.object(intraday_module, "send_trade_email_notification"):
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)
                    status = intraday_module.run_intraday_pipeline(dry_run=False)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertTrue(load_policy_inputs.called)
        kwargs = load_policy_inputs.call_args.kwargs
        self.assertTrue(kwargs["require_live_quotes"])
        self.assertIsNotNone(kwargs["quote_provider"])

    def test_review_mode_uses_deterministic_path(self) -> None:
        # review now uses the SAME deterministic engine as paper; on no would_trade
        # it only fetches the snapshot (no execute prompt).
        no_trade = PolicyDecision(
            trading_mode="review", checked_symbols=["NVDA"], decision="no_action", reason="no candidate",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs") as load_policy_inputs, \
                    mock.patch.object(intraday_module, "generate_order_intent", return_value=no_trade), \
                    mock.patch.object(intraday_module, "_run_shadow_experiments_safely"), \
                    mock.patch.object(intraday_module, "run_codex_prompt", return_value=0) as run_codex_prompt:
                    load_runtime_config.return_value = mock.Mock(trading_mode="review", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)
                    load_policy_inputs.return_value = policy_ready_inputs(trading_mode="review")

                    status = intraday_module.run_intraday_pipeline(dry_run=False)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        load_policy_inputs.assert_called_once()
        run_kinds = [call.args[0] for call in run_codex_prompt.call_args_list]
        self.assertEqual(run_kinds, ["intraday_snapshot"])  # no would_trade -> no execute

    def test_deterministic_live_shares_decision_and_only_executes(self) -> None:
        # Flag on: live must use the deterministic engine (load_policy_inputs +
        # generate_order_intent) and place via snapshot+execute prompts — NOT the
        # legacy analysis "intraday" prompt.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            intent = OrderIntent(
                symbol="NVDA", side="buy", order_type="limit",
                limit_price=100.0, estimated_notional=100.0, quantity=1.0,
            )
            would_trade = PolicyDecision(
                trading_mode="live", checked_symbols=["NVDA"], decision="would_trade",
                intent=intent, reason="policy buy intent generated",
            )
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.dict(os.environ, {"ENABLE_DETERMINISTIC_INTRADAY": "1"}, clear=False), \
                    mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs") as load_policy_inputs, \
                    mock.patch.object(intraday_module, "generate_order_intent", return_value=would_trade), \
                    mock.patch.object(intraday_module, "_run_shadow_experiments_safely"), \
                    mock.patch.object(intraday_module, "run_codex_prompt", return_value=0) as run_codex_prompt:
                    load_runtime_config.return_value = mock.Mock(trading_mode="live", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)
                    load_policy_inputs.return_value = policy_ready_inputs(trading_mode="live")

                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        load_policy_inputs.assert_called_once()
        run_kinds = [call.args[0] for call in run_codex_prompt.call_args_list]
        self.assertEqual(run_kinds, ["intraday_snapshot", "intraday_execute"])
        self.assertNotIn("intraday", run_kinds)
        self.assertEqual(decisions[-1]["action_taken"], "live_order_submitted")

    def test_live_dry_run_skips_intraday_codex_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "run_codex_prompt") as run_codex_prompt:
                    load_runtime_config.return_value = mock.Mock(trading_mode="live", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)

                    status = intraday_module.run_intraday_pipeline(dry_run=True)
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        run_codex_prompt.assert_not_called()
        self.assertEqual(decisions[0]["decision"], "dry_run_skip")
        self.assertEqual(decisions[0]["reason"], "dry_run_non_paper_prompt_skipped")

    def test_existing_kill_switch_skip_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            (root / "KILL_SWITCH").write_text("", encoding="utf-8")
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "load_policy_inputs", return_value=policy_ready_inputs()):
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)
                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(decisions[0]["decision"], "would_trade")

    def test_pending_paper_order_blocks_duplicate_submission_on_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_repo_root(root)
            original_cwd = os.getcwd()
            os.chdir(root)
            try:
                pending_inputs = policy_ready_inputs()
                pending_decision = PolicyDecision(
                    trading_mode="paper",
                    checked_symbols=["NVDA"],
                    decision="would_trade",
                    intent=OrderIntent(
                        symbol="NVDA",
                        side="buy",
                        order_type="limit",
                        limit_price=100.0,
                        reference_price=101.0,
                        estimated_notional=10.0,
                        quantity=0.1,
                    ),
                )
                with mock.patch.dict(os.environ, {"PAPER_FILL_MODEL": "conservative"}, clear=False):
                    apply_paper_intent(root, run_date="2026-06-14", decision=pending_decision, starting_cash=400000.0)
                (root / "src" / "config").mkdir(parents=True, exist_ok=True)
                planner_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "planner"
                planner_dir.mkdir(parents=True, exist_ok=True)
                (root / "src" / "config" / "universe.txt").write_text("NVDA\n", encoding="utf-8")
                write_json(root / "src" / "config" / "risk_tiers.json", {"0": {"max_single_order_notional": 10, "max_daily_notional": 25}})
                (planner_dir / "today_allowlist.txt").write_text("NVDA\n", encoding="utf-8")
                write_json(planner_dir / "daily_plan.json", pending_inputs.daily_plan)
                write_json(planner_dir / "candidate_scores.json", pending_inputs.candidate_scores)
                write_json(planner_dir / "risk_overlay.json", pending_inputs.risk_overlay)
                write_json(planner_dir / "trader_watch_levels.json", pending_inputs.trader_watch_levels)
                write_json(planner_dir / "data_status_summary.json", pending_inputs.data_status_summary)
                write_json(planner_dir / "capital_snapshot.json", pending_inputs.capital_snapshot)
                write_json(planner_dir / "catalyst_snapshot.json", pending_inputs.catalyst_snapshot)
                signals_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "signals"
                paper_dir = root / "runtime" / "state" / "runs" / "2026-06-14" / "paper"
                write_json(signals_dir / "technical_signals.json", pending_inputs.technical_signals)
                write_json(planner_dir / "quote_snapshot_core.json", {"date": "2026-06-14", "symbols": {"NVDA": {"last_price": 101.0, "previous_close": 101.0, "timestamp": datetime.now(tz=PT).isoformat(), "is_fresh": True}}})
                write_json(paper_dir / "account.json", {"cash": 400000.0})
                write_json(paper_dir / "positions.json", {})
                with mock.patch.object(intraday_module, "_is_weekday_pt", return_value=True), \
                    mock.patch.object(intraday_module, "_is_intraday_window_pt", return_value=True), \
                    mock.patch.object(intraday_module, "pt_date_string", return_value="2026-06-14"), \
                    mock.patch.object(intraday_module, "load_runtime_config") as load_runtime_config, \
                    mock.patch.object(intraday_module, "send_trade_email_notification"):
                    load_runtime_config.return_value = mock.Mock(trading_mode="paper", risk_tier=0, paper_risk_tier=0, effective_risk_tier=0)
                    status = intraday_module.run_intraday_pipeline(dry_run=False)
                    decisions = read_decisions(root)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(status, 0)
        self.assertEqual(decisions[-1]["decision"], "blocked")
        self.assertIn("open_order_exists", decisions[-1]["blocked_reasons"])


if __name__ == "__main__":
    unittest.main()
