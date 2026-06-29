from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from trading_agent.core.context import resolve_agent_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading_agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("premarket", "intraday", "postmarket", "dsa"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--dry-run", action="store_true")

    subparsers.add_parser(
        "nightly-analysis",
        help="Run the read-only/shadow-only nightly analytics batch.",
    )

    subparsers.add_parser("doctor", help="Print effective runtime configuration and exit.")

    replay_parser = subparsers.add_parser("replay", help="Print local fill-rate and blocked-reason replay report.")
    replay_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None, help="Only include run dates on or after this date.")
    replay_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None, help="Only include run dates on or before this date.")
    replay_parser.add_argument("--output", metavar="PATH", default=None, help="Write JSON report to this path instead of printing text.")

    analytics_parser = subparsers.add_parser("analytics", help="Build the local analytics.db from runtime/state/runs/*.")
    analytics_subparsers = analytics_parser.add_subparsers(dest="analytics_command", required=True)
    analytics_build_parser = analytics_subparsers.add_parser("build", help="(Re)build runtime/analytics/analytics.db.")
    analytics_build_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None, help="Only include run dates on or after this date.")
    analytics_build_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None, help="Only include run dates on or before this date.")
    analytics_calibrate_parser = analytics_subparsers.add_parser("calibrate", help="Write runtime/analytics/calibration_report.{json,md} (E1: forward returns + attribution; needs network for yfinance).")
    analytics_calibrate_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_calibrate_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_fill_quality_parser = analytics_subparsers.add_parser("fill-quality", help="Write runtime/analytics/fill_quality_report.{json,md} (E4: realized slippage + conservative-fill sensitivity; local-only).")
    analytics_fill_quality_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_fill_quality_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_ai_study_parser = analytics_subparsers.add_parser("ai-signal-study", help="Write runtime/analytics/ai_signal_study.{json,md} (H3: AI-signal confidence calibration + directional accuracy + code lift; needs network for yfinance).")
    analytics_ai_study_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_ai_study_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_ai_ablation_parser = analytics_subparsers.add_parser("ai-ablation", help="Write runtime/analytics/ai_ablation.{json,md} (H3: per-AI-layer marginal IC via leave-one-out + AI-vs-factor; needs network for yfinance).")
    analytics_ai_ablation_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_ai_ablation_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_snapshot_parser = analytics_subparsers.add_parser("snapshot", help="Archive a dated copy of tonight's reports to runtime/analytics/history/<date>/ + nightly_summary.json (I2).")
    analytics_snapshot_parser.add_argument("--date", metavar="YYYY-MM-DD", default=None, help="Snapshot date label (default: today PT).")
    analytics_trend_parser = analytics_subparsers.add_parser("trend", help="Aggregate history/*/nightly_summary.json into per-metric time series (I3).")
    analytics_trend_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_trend_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_trend_parser.add_argument("--output", metavar="PATH", default=None, help="Write JSON to this path instead of the default trend.json.")
    analytics_weights_parser = analytics_subparsers.add_parser("weight-suggestion", help="Write runtime/analytics/weight_suggestion.json (E2: IC-backed scoring-weight SUGGESTION — never auto-applied).")
    analytics_weights_parser.add_argument("--horizon", metavar="DAYS", default=None, help="Horizon (e.g. 1/5/21) to read component IC from; default: first calibrated horizon.")
    analytics_weights_parser.add_argument("--damping", type=float, default=0.5, help="Tilt strength 0..1 (0 = no change, 1 = full IC tilt). Default 0.5.")
    analytics_subparsers.add_parser("nightly-health", help="Write runtime/analytics/nightly_health.json (L4: report freshness + last nightly run's failed steps).")
    analytics_thesis_parser = analytics_subparsers.add_parser("thesis", help="Write runtime/analytics/thesis_attribution.{json,md} (K3: per-thesis win rate / mean forward return; needs network for yfinance).")
    analytics_thesis_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_thesis_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_screen_eval_parser = analytics_subparsers.add_parser("screen-eval", help="Write runtime/analytics/screen_eval_report.{json,md} (O4: selection-layer effectiveness — added/demoted forward returns vs SPY + screen_score Rank IC; needs network for yfinance).")
    analytics_screen_eval_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_screen_eval_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_setup_screen_parser = analytics_subparsers.add_parser("setup-screen", help="Write runtime/analytics/setup_screen.{json,md} (Q1: replay each entry setup over all historical candidates+key_levels → hypothetical fills / win-rate / forward-return table; needs network for yfinance).")
    analytics_setup_screen_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_setup_screen_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_setup_screen_parser.add_argument("--setups", metavar="A,B,C", default=None, help="Comma-separated setup stack to screen as ONE strategy (first-clears-wins). Default: screen every registered setup in isolation, head-to-head.")
    analytics_setup_screen_parser.add_argument("--profile", metavar="NAME", default=None, help="Screen this policy_profile's configured setups instead of a raw stack.")
    analytics_setup_screen_parser.add_argument("--lookahead", type=int, default=5, help="Trading-day horizon for target/stop + forward return (default 5).")
    analytics_setup_screen_parser.add_argument("--max-per-day", type=int, default=None, help="Cap hypothetical fills per day (default: all eligible candidates).")
    analytics_setup_screen_parser.add_argument("--split-date", metavar="YYYY-MM-DD", default=None, help="Q5: split into TRAIN (before) vs held-out TEST (on/after) windows to catch overfitting.")
    analytics_discover_parser = analytics_subparsers.add_parser("discover", help="Write runtime/analytics/discovery.{json,md} (Q4: mine history for setups to BUILD — which gate blocks winners, top missed winners, near-threshold; needs network for yfinance).")
    analytics_discover_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_discover_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_discover_parser.add_argument("--lookahead", type=int, default=5, help="Forward-return horizon in trading days (default 5).")
    analytics_discover_parser.add_argument("--top-k", type=int, default=20, help="How many top missed-winner rows to list (default 20).")
    analytics_validate_parser = analytics_subparsers.add_parser("validate", help="Write runtime/analytics/validate_report.{json,md} (N3: read-only scan for malformed JSONL lines + rows missing key fields; local-only, modifies nothing).")
    analytics_validate_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    analytics_validate_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    analytics_retention_parser = analytics_subparsers.add_parser("retention", help="Write runtime/analytics/retention_report.{json,md} (N4: prune big premarket input snapshots (market_feed) from runs older than --keep-days; DRY-RUN unless --apply).")
    analytics_retention_parser.add_argument("--keep-days", type=int, default=60, help="Keep runs within this many days fully intact (default 60).")
    analytics_retention_parser.add_argument("--apply", action="store_true", help="Actually delete the prunable artifacts. Without this flag it is a dry-run (report only).")

    subparsers.add_parser("dashboard", help="Launch the read-only Streamlit dashboard at http://localhost:8501.")

    screen_parser = subparsers.add_parser(
        "screen",
        help="O1 weekly Serenity-skill stock screener: discover pool-external bottleneck stocks "
        "→ factor-validate → auto-update universe (add-only + re-rank).",
    )
    screen_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force report-only: never write universe.txt/universe_meta.json.",
    )
    screen_parser.add_argument(
        "--apply",
        action="store_true",
        help="Force auto-apply (write the universe). --dry-run wins if both given.",
    )

    growth_parser = subparsers.add_parser("growth", help="Self-growth diagnostics (paper-only, read-only).")
    growth_subparsers = growth_parser.add_subparsers(dest="growth_command", required=True)
    growth_observe_parser = growth_subparsers.add_parser("observe", help="Write runtime/analytics/growth_observations.json.")
    growth_observe_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    growth_observe_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    growth_propose_parser = growth_subparsers.add_parser("propose", help="Write validated, whitelist-only strategy proposals (never auto-enabled).")
    growth_propose_parser.add_argument("--since", metavar="YYYY-MM-DD", default=None)
    growth_propose_parser.add_argument("--until", metavar="YYYY-MM-DD", default=None)
    growth_validate_parser = growth_subparsers.add_parser("validate", help="Validate a proposal JSON (or a whole proposals dir) against growth_policy.")
    growth_validate_parser.add_argument("path", metavar="PROPOSAL_OR_DIR", help="Path to a proposal_*.json file or a runtime/strategy_proposals/<date>/ directory.")

    experiments_parser = growth_subparsers.add_parser("experiments", help="Manage the shadow-experiment queue (approve only enables shadow, never live).")
    experiments_subparsers = experiments_parser.add_subparsers(dest="experiments_command", required=True)
    exp_list = experiments_subparsers.add_parser("list", help="List queued experiments.")
    exp_list.add_argument("--status", default=None, help="Filter by lifecycle status.")
    exp_add = experiments_subparsers.add_parser("add", help="Enqueue a validated proposal JSON as a new experiment (state: proposed).")
    exp_add.add_argument("proposal", metavar="PROPOSAL_JSON")
    exp_add.add_argument("--parent", default=None, help="Parent (champion) strategy_id; defaults to the active strategy.")
    for action in ("approve", "reject", "archive"):
        exp_action = experiments_subparsers.add_parser(action, help=f"{action} an experiment by id.")
        exp_action.add_argument("experiment_id", metavar="EXPERIMENT_ID")

    growth_shadow_parser = growth_subparsers.add_parser("shadow", help="Run active_shadow challengers over the current run's champion inputs (isolated ledgers).")
    growth_shadow_parser.add_argument("--run-date", metavar="YYYY-MM-DD", default=None)
    for name, helptext in (("evaluate", "Write experiment_report.json + promotion_recommendation.md (recommend-only)."),
                           ("recommend", "Same as evaluate, then print the promotion recommendation.")):
        ev = growth_subparsers.add_parser(name, help=helptext)
        ev.add_argument("--since", metavar="YYYY-MM-DD", default=None)
        ev.add_argument("--until", metavar="YYYY-MM-DD", default=None)

    promote_parser = growth_subparsers.add_parser("promote", help="Human-in-the-loop promotion: validate + draft only (never edits strategy_registry.yaml).")
    promote_subparsers = promote_parser.add_subparsers(dest="promote_command", required=True)
    promote_check = promote_subparsers.add_parser("check", help="Validate a challenger and write a changelog + registry draft.")
    promote_check.add_argument("experiment_id", metavar="EXPERIMENT_ID")

    return parser


def _launchd_status_lines(agent_root: Path) -> list[str]:
    """Report whether each launchd job template is currently loaded.

    Reads the <Label> from each launchd/*.plist.example and checks it against
    `launchctl list`. Best-effort and non-fatal: on non-macOS (no launchctl) or
    when templates are absent, it just notes that the check was skipped.
    """
    import re
    import shutil
    import subprocess

    template_dir = agent_root / "launchd"
    templates = sorted(template_dir.glob("*.plist.example")) if template_dir.is_dir() else []
    if not templates:
        return ["  (no launchd/*.plist.example templates found — skipped)"]

    def read_label(path: Path) -> str | None:
        text = path.read_text(encoding="utf-8")
        match = re.search(r"<key>Label</key>\s*<string>([^<]+)</string>", text)
        return match.group(1) if match else None

    labels = [(path, read_label(path)) for path in templates]

    launchctl = shutil.which("launchctl")
    if not launchctl:
        lines = ["  launchctl not found (not macOS) — load state unknown:"]
        for _path, label in labels:
            lines.append(f"    {label or '?'}")
        return lines

    try:
        listed = subprocess.run(
            [launchctl, "list"], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - environment dependent
        return [f"  could not run launchctl list: {exc}"]

    lines = []
    any_missing = False
    for _path, label in labels:
        if not label:
            continue
        loaded = label in listed
        if not loaded:
            any_missing = True
        lines.append(f"  {'loaded   ' if loaded else 'NOT LOADED'}  {label}")
    if any_missing:
        lines.append("  → install/reload with: src/scripts/launchd/install_launchd_jobs.sh")
    return lines


def _run_doctor(agent_root: Path) -> int:
    from trading_agent.core.config import TierMisconfigurationError, load_runtime_config
    from trading_agent.strategy.registry import load_active_strategy

    config = load_runtime_config(agent_root)
    env = os.environ
    active_strategy = load_active_strategy(agent_root)

    tier_misconfigured = False
    try:
        effective_tier_line = (
            f"  effective_risk_tier now   = {config.effective_risk_tier}  (based on TRADING_MODE)"
        )
    except TierMisconfigurationError as exc:
        tier_misconfigured = True
        effective_tier_line = f"  effective_risk_tier now   = FAIL-CLOSED: {exc}"

    risk_tiers_path = agent_root / "src" / "config" / "risk_tiers.json"
    risk_tiers: dict = {}
    if risk_tiers_path.exists():
        risk_tiers = json.loads(risk_tiers_path.read_text(encoding="utf-8"))

    def tier_caps(tier: int) -> str:
        caps = risk_tiers.get(str(tier), {})
        single = caps.get("max_single_order_notional", "?")
        daily = caps.get("max_daily_notional", "?")
        name = caps.get("name", "unknown")
        return f"tier {tier} ({name}): max_single=${single}  max_daily=${daily}"

    kill_switch = (agent_root / "KILL_SWITCH").exists()

    lines = [
        "=== Trading Agent — Effective Configuration ===",
        "",
        f"  TRADING_MODE              = {config.trading_mode}",
        f"  KILL_SWITCH               = {'ACTIVE (file present)' if kill_switch else 'inactive'}",
        "",
        "  --- Strategy ---",
        f"  active_strategy            = {active_strategy['strategy_id']}  [{active_strategy['status']}]",
        f"  change_reason              = {active_strategy['change_reason']}",
        "",
        "  --- Risk Tiers ---",
        f"  RISK_TIER (live/review)   = {config.risk_tier}  [{tier_caps(config.risk_tier)}]",
        f"  PAPER_RISK_TIER           = {config.paper_risk_tier}  [{tier_caps(config.paper_risk_tier)}]",
        effective_tier_line,
        "",
        "  --- Codex ---",
        f"  CODEX_MODEL               = {env.get('CODEX_MODEL', 'gpt-5.4')}",
        f"  CODEX_MODEL_MINI          = {env.get('CODEX_MODEL_MINI', 'gpt-5.4')}",
        f"  CODEX_BIN                 = {env.get('CODEX_BIN', 'codex')}",
        f"  CODEX_EXEC_TIMEOUT_SEC    = {env.get('CODEX_EXEC_TIMEOUT_SEC', '3600')}",
        f"  CODEX_EXEC_DRY_RUN        = {env.get('CODEX_EXEC_DRY_RUN', '0')}",
        "",
        "  --- Signal Layers (always on) ---",
        f"  DSA_MAX_SUBAGENTS         = {env.get('DSA_MAX_SUBAGENTS', '3')}",
        f"  DSA_METRICS_LOOKBACK_DAYS = {env.get('DSA_METRICS_LOOKBACK_DAYS', '180')}",
        f"  MARKET_FEED_TIMEFRAMES    = {config.market_feed_timeframes}",
        f"  TECHNICAL_MAX_SUBAGENTS   = {env.get('TECHNICAL_MAX_SUBAGENTS', '3')}",
        f"  TECHNICAL_RECENT_BARS     = {env.get('TECHNICAL_RECENT_BARS', '30')}",
        f"  TECHNICAL_LLM_MAX_SWING   = {env.get('TECHNICAL_LLM_MAX_SWING', '12')}",
        "",
        "  --- Paper ---",
        f"  PAPER_STARTING_CASH       = {env.get('PAPER_STARTING_CASH', '400000')}",
        f"  PAPER_FILL_MODEL          = {env.get('PAPER_FILL_MODEL', 'conservative')}",
        f"  PAPER_PARTIAL_FILL        = {env.get('PAPER_PARTIAL_FILL', '0')}",
        f"  PAPER_PARTIAL_FILL_MIN_RATIO     = {env.get('PAPER_PARTIAL_FILL_MIN_RATIO', '0.3')}",
        f"  PAPER_PARTIAL_FILL_THRESHOLD_BPS = {env.get('PAPER_PARTIAL_FILL_THRESHOLD_BPS', '20')}",
        f"  PAPER_SLIPPAGE_BPS        = {env.get('PAPER_SLIPPAGE_BPS', '10')}",
        f"  LIVE_QUOTES_CAPTURE_BOOK  = {env.get('LIVE_QUOTES_CAPTURE_BOOK', '0')}",
        f"  ENABLE_INTRADAY_BAR_CAPTURE = {env.get('ENABLE_INTRADAY_BAR_CAPTURE', '0')}  (Q6: per-tick intraday bars → intraday_bars.jsonl; off by default)",
        f"  HARD_STOP_LOSS_PCT        = {env.get('HARD_STOP_LOSS_PCT', '0.08')}",
        "",
        "  --- Selection Layer (weekly screener · O1) ---",
        f"  SCREEN_MAX_ADDS_PER_WEEK  = {env.get('SCREEN_MAX_ADDS_PER_WEEK', '5')}",
        f"  UNIVERSE_MAX              = {env.get('UNIVERSE_MAX', '120')}",
        f"  SCREEN_MIN_DOLLAR_VOL     = {env.get('SCREEN_MIN_DOLLAR_VOL', '20000000')}",
        f"  SCREEN_REQUIRE_UPTREND    = {env.get('SCREEN_REQUIRE_UPTREND', '1')}",
        f"  ACTIVE_MAX                = {env.get('ACTIVE_MAX', '30')}",
        "",
        "  --- Scheduling (launchd) ---",
        *_launchd_status_lines(agent_root),
    ]

    print("\n".join(lines))
    return 2 if tier_misconfigured else 0


def _run_replay(agent_root: Path, *, since: str | None, until: str | None, output: str | None) -> int:
    from trading_agent.replay.analysis import build_replay_report, format_replay_report

    report = build_replay_report(agent_root, since_date=since, until_date=until)
    if output:
        Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Replay report written to {output}")
    else:
        print(format_replay_report(report))
    return 0


def _run_analytics_build(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.analytics.build_db import build_analytics_db, default_analytics_db_path

    row_counts = build_analytics_db(agent_root, since_date=since, until_date=until)
    print(f"Wrote {default_analytics_db_path(agent_root)}")
    for table_name, count in row_counts.items():
        print(f"  {table_name:<15} {count} rows")
    return 0


def _run_growth_observe(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.growth.observations import write_growth_observations

    path = write_growth_observations(agent_root, since=since, until=until)
    print(f"Wrote {path}")
    return 0


def _run_growth_propose(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.growth.proposals import write_proposals

    written = write_proposals(agent_root, since=since, until=until)
    if not written:
        print("No proposals generated (no actionable observations within the safety whitelist).")
        return 0
    print(f"Wrote {len(written)} proposal(s):")
    for path in written:
        print(f"  {path}")
    return 0


def _run_growth_validate(agent_root: Path, *, path: str) -> int:
    from trading_agent.growth.proposal_review import validate_proposal_file, validate_proposals_dir

    target = Path(path)
    if not target.exists():
        print(f"No such path: {target}")
        return 1
    written = [validate_proposal_file(agent_root, target)] if target.is_file() else validate_proposals_dir(agent_root, target)
    if not written:
        print("No proposal_*.json files found to validate.")
        return 0
    import json as _json

    for out_path in written:
        result = _json.loads(out_path.read_text(encoding="utf-8"))
        print(f"  {result.get('status', '?'):<10} {out_path}")
    return 0


def _run_growth_experiments(agent_root: Path, args) -> int:
    from trading_agent.growth import experiment_queue as eq

    command = args.experiments_command
    if command == "list":
        rows = eq.list_experiments(agent_root, status=args.status)
        if not rows:
            print("No experiments queued.")
            return 0
        for row in rows:
            print(f"  {row['status']:<16} {row['experiment_id']}  (challenger: {row.get('challenger_strategy_id')})")
        return 0
    if command == "add":
        import json as _json
        from trading_agent.strategy.registry import load_active_strategy

        proposal = _json.loads(Path(args.proposal).read_text(encoding="utf-8"))
        parent = args.parent or load_active_strategy(agent_root)["strategy_id"]
        exp = eq.add_experiment(agent_root, proposal, parent_strategy_id=parent)
        print(f"Queued {exp['experiment_id']} (status: {exp['status']}, parent: {parent})")
        return 0
    handler = {"approve": eq.approve_experiment, "reject": eq.reject_experiment, "archive": eq.archive_experiment}[command]
    try:
        exp = handler(agent_root, args.experiment_id)
    except KeyError:
        print(f"No such experiment: {args.experiment_id}")
        return 1
    except eq.ExperimentTransitionError as exc:
        print(f"Refused: {exc}")
        return 2
    print(f"{args.experiment_id} -> {exp['status']}")
    return 0


def _run_growth_shadow(agent_root: Path, *, run_date: str | None) -> int:
    from trading_agent.core.config import load_runtime_config
    from trading_agent.core.time import pt_date_string
    from trading_agent.data.live_quotes import fetch_yfinance_live_quotes
    from trading_agent.growth.experiment_queue import list_experiments
    from trading_agent.growth.shadow_runner import run_active_shadow_experiments
    from trading_agent.policy.loaders import load_policy_inputs

    resolved_run_date = run_date or pt_date_string()
    active = list_experiments(agent_root, status="active_shadow")
    if not active:
        print("No active_shadow experiments to run.")
        return 0
    runtime = load_runtime_config(agent_root)
    inputs = load_policy_inputs(
        agent_root,
        run_date=resolved_run_date,
        trading_mode=runtime.trading_mode,
        risk_tier=runtime.effective_risk_tier,
        quote_provider=fetch_yfinance_live_quotes,
        require_live_quotes=True,
    )
    results = run_active_shadow_experiments(
        agent_root, run_date=resolved_run_date, champion_inputs=inputs,
        trading_mode=runtime.trading_mode, risk_tier=runtime.effective_risk_tier,
    )
    for result in results:
        if result.get("error"):
            print(f"  ERROR {result.get('experiment_id')}: {result['error']}")
        else:
            print(f"  {result.get('decision', '?'):<12} {result.get('challenger_strategy_id')} (symbol: {result.get('symbol')})")
    return 0


def _run_growth_evaluate(agent_root: Path, *, since: str | None, until: str | None, print_md: bool) -> int:
    from trading_agent.growth.evaluator import write_experiment_report

    json_path, md_path = write_experiment_report(agent_root, since=since, until=until)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    if print_md:
        print()
        print(md_path.read_text(encoding="utf-8"))
    return 0


def _run_growth_promote_check(agent_root: Path, *, experiment_id: str) -> int:
    from trading_agent.growth.promotion import build_promotion_check, write_promotion_check

    try:
        check = build_promotion_check(agent_root, experiment_id)
    except KeyError:
        print(f"No such experiment: {experiment_id}")
        return 1
    out_path = write_promotion_check(agent_root, experiment_id)
    verdict = "ELIGIBLE for human promotion" if check["eligible"] else "NOT eligible"
    print(f"{experiment_id}: {verdict}")
    for reason in check["blocking_reasons"]:
        print(f"  - {reason}")
    print(f"Draft written to {out_path}")
    print("Promotion stays a manual strategy_registry.yaml edit — this command changed nothing.")
    return 0


def _run_analytics_calibrate(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.replay.calibration import write_calibration_report

    json_path, md_path = write_calibration_report(agent_root, since=since, until=until)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def _run_analytics_fill_quality(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.replay.fill_quality import write_fill_quality_report

    json_path, md_path = write_fill_quality_report(agent_root, since=since, until=until)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def _run_analytics_ai_signal_study(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.replay.ai_signal_study import write_ai_signal_study_report

    json_path, md_path = write_ai_signal_study_report(agent_root, since=since, until=until)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def _run_analytics_ai_ablation(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.replay.ai_ablation import write_ai_ablation_report

    json_path, md_path = write_ai_ablation_report(agent_root, since=since, until=until)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def _run_analytics_snapshot(agent_root: Path, *, date: str | None) -> int:
    from trading_agent.analytics.snapshot import write_analysis_snapshot

    dest = write_analysis_snapshot(agent_root, date=date)
    print(f"Wrote snapshot {dest}")
    return 0


def _run_analytics_trend(agent_root: Path, *, since: str | None, until: str | None, output: str | None) -> int:
    from trading_agent.analytics.trend import write_trend

    out = write_trend(agent_root, since=since, until=until, output=Path(output) if output else None)
    print(f"Wrote {out}")
    return 0


def _run_analytics_weight_suggestion(agent_root: Path, *, horizon: str | None, damping: float) -> int:
    from trading_agent.analytics.weight_suggestion import write_weight_suggestion_report

    out = write_weight_suggestion_report(agent_root, horizon=horizon, damping=damping)
    print(f"Wrote {out}  (suggestion only — never auto-applied)")
    return 0


def _run_analytics_nightly_health(agent_root: Path) -> int:
    from trading_agent.analytics.nightly_health import build_nightly_health, write_nightly_health

    out = write_nightly_health(agent_root)
    health = build_nightly_health(agent_root)
    print(f"Wrote {out}  (status: {health['status']}"
          + (f", stale: {health['stale_reports']}" if health['stale_reports'] else "")
          + (f", failed: {health['failed_steps']}" if health['failed_steps'] else "") + ")")
    return 0


def _run_analytics_validate(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.analytics.validate import write_validate_report

    out, report = write_validate_report(agent_root, since=since, until=until)
    print(f"Wrote {out}  (status: {report['status']}"
          f", malformed: {report['total_malformed']}"
          f", missing_key: {report['total_missing_key']})")
    return 0


def _run_analytics_retention(agent_root: Path, *, keep_days: int, apply: bool) -> int:
    from trading_agent.analytics.retention import write_retention_report

    out, report = write_retention_report(agent_root, keep_days=keep_days, apply=apply)
    reclaim_mb = report["total_reclaim_bytes"] / (1024 * 1024)
    mode = "APPLIED" if apply else "dry-run"
    msg = (f"Wrote {out}  ({mode}: {report['prune_run_count']} prunable runs, "
           f"{reclaim_mb:.1f} MB reclaimable")
    if apply and "applied" in report:
        applied_mb = report["applied"]["reclaimed_bytes"] / (1024 * 1024)
        msg += f"; removed {report['applied']['removed_dirs']} dirs, {applied_mb:.1f} MB freed"
    print(msg + ")")
    if not apply and report["prune_run_count"]:
        print("  (dry-run: pass --apply to actually delete)")
    return 0


def _run_analytics_thesis(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.replay.thesis import write_thesis_attribution

    json_path, md_path = write_thesis_attribution(agent_root, since=since, until=until)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def _run_analytics_screen_eval(agent_root: Path, *, since: str | None, until: str | None) -> int:
    from trading_agent.replay.screen_eval import write_screen_eval_report

    json_path, md_path = write_screen_eval_report(agent_root, since=since, until=until)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def _run_analytics_setup_screen(
    agent_root: Path,
    *,
    since: str | None,
    until: str | None,
    setups: str | None,
    profile: str | None,
    lookahead: int,
    max_per_day: int | None,
    split_date: str | None,
) -> int:
    from trading_agent.replay.setup_screen import write_setup_screen_report

    setup_list = [name.strip() for name in setups.split(",") if name.strip()] if setups else None
    json_path, md_path = write_setup_screen_report(
        agent_root,
        lookahead=lookahead,
        since=since,
        until=until,
        profile_name=profile,
        setups=setup_list,
        max_per_day=max_per_day,
        split_date=split_date,
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def _run_analytics_discover(agent_root: Path, *, since: str | None, until: str | None, lookahead: int, top_k: int) -> int:
    from trading_agent.replay.discovery import write_discovery_report

    json_path, md_path = write_discovery_report(agent_root, lookahead=lookahead, since=since, until=until, top_k=top_k)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def _run_nightly_analysis(agent_root: Path) -> int:
    from trading_agent.core.config import load_env_files
    from trading_agent.core.context import build_runtime_paths
    from trading_agent.core.time import pt_now

    load_env_files(agent_root)
    paths = build_runtime_paths(agent_root)
    nightly_log_dir = paths.run_logs_dir / "nightly"
    nightly_log_dir.mkdir(parents=True, exist_ok=True)
    paths.error_log_path.parent.mkdir(parents=True, exist_ok=True)
    analysis_log = nightly_log_dir / "analysis.log"
    step_results = nightly_log_dir / "step_results.jsonl"
    step_results.write_text("", encoding="utf-8")

    env = {
        **os.environ,
        "AGENT_ROOT": str(agent_root),
        "PYTHONPATH": f"{agent_root / 'src'}:{os.environ.get('PYTHONPATH', '')}",
    }

    def timestamp() -> str:
        return pt_now().strftime("%Y-%m-%dT%H:%M:%S%z")

    def append(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)

    def run_step(label: str, argv: list[str]) -> None:
        append(analysis_log, f"{timestamp()} [nightly] START {label}\n")
        with analysis_log.open("a", encoding="utf-8") as log_handle:
            result = subprocess.run(
                [sys.executable, "-m", "trading_agent", *argv],
                cwd=agent_root,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        status = "ok" if result.returncode == 0 else "fail"
        marker = "OK   " if result.returncode == 0 else "FAIL "
        append(analysis_log, f"{timestamp()} [nightly] {marker} {label}"
                             + (f" (exit {result.returncode})" if result.returncode else "") + "\n")
        if result.returncode:
            append(paths.error_log_path, f"{timestamp()} nightly step failed: {label} (exit {result.returncode})\n")
        append(step_results, json.dumps(
            {"step": label, "status": status, "exit_code": result.returncode, "timestamp": timestamp()},
            ensure_ascii=True,
        ) + "\n")

    print(f"nightly analysis starting (date={paths.run_date}, log={analysis_log})")

    steps = [
        ("analytics build", ["analytics", "build"]),
        ("analytics calibrate", ["analytics", "calibrate"]),
        ("analytics fill-quality", ["analytics", "fill-quality"]),
        ("analytics ai-signal-study", ["analytics", "ai-signal-study"]),
        ("analytics ai-ablation", ["analytics", "ai-ablation"]),
        ("analytics thesis", ["analytics", "thesis"]),
        ("analytics screen-eval", ["analytics", "screen-eval"]),
        ("analytics setup-screen", ["analytics", "setup-screen"]),
        ("analytics discover", ["analytics", "discover"]),
        ("analytics weight-suggestion", ["analytics", "weight-suggestion"]),
        ("growth observe", ["growth", "observe"]),
        ("growth propose", ["growth", "propose"]),
    ]
    for label, argv in steps:
        run_step(label, argv)

    proposals_dir = agent_root / "runtime" / "strategy_proposals" / paths.run_date
    if proposals_dir.is_dir():
        run_step("growth validate", ["growth", "validate", str(proposals_dir)])

    for label, argv in [
        ("growth shadow", ["growth", "shadow"]),
        ("growth evaluate", ["growth", "evaluate"]),
        ("analytics snapshot", ["analytics", "snapshot"]),
        ("analytics trend", ["analytics", "trend"]),
        ("analytics nightly-health", ["analytics", "nightly-health"]),
    ]:
        run_step(label, argv)

    print(f"nightly analysis finished (date={paths.run_date}, log={analysis_log})")
    return 0


def _run_dashboard(agent_root: Path) -> int:
    app_path = Path(__file__).resolve().parent / "dashboard" / "app.py"
    env = {**os.environ, "PYTHONPATH": f"{agent_root / 'src'}:{os.environ.get('PYTHONPATH', '')}"}
    return subprocess.call(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        cwd=agent_root,
        env=env,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    agent_root = resolve_agent_root()
    if args.command == "premarket":
        from trading_agent.orchestration.premarket import run_premarket_pipeline

        return run_premarket_pipeline(dry_run=args.dry_run)
    if args.command == "intraday":
        from trading_agent.orchestration.intraday import run_intraday_pipeline

        return run_intraday_pipeline(dry_run=args.dry_run)
    if args.command == "postmarket":
        from trading_agent.orchestration.postmarket import run_postmarket_pipeline

        return run_postmarket_pipeline(dry_run=args.dry_run)
    if args.command == "dsa":
        from trading_agent.signals.dsa import run_dsa_scan

        if args.dry_run:
            os.environ["CODEX_EXEC_DRY_RUN"] = "1"
        run_dsa_scan(agent_root)
        return 0
    if args.command == "nightly-analysis":
        return _run_nightly_analysis(agent_root)
    if args.command == "doctor":
        return _run_doctor(agent_root)
    if args.command == "replay":
        return _run_replay(agent_root, since=args.since, until=args.until, output=args.output)
    if args.command == "analytics" and args.analytics_command == "build":
        return _run_analytics_build(agent_root, since=args.since, until=args.until)
    if args.command == "analytics" and args.analytics_command == "calibrate":
        return _run_analytics_calibrate(agent_root, since=args.since, until=args.until)
    if args.command == "analytics" and args.analytics_command == "fill-quality":
        return _run_analytics_fill_quality(agent_root, since=args.since, until=args.until)
    if args.command == "analytics" and args.analytics_command == "ai-signal-study":
        return _run_analytics_ai_signal_study(agent_root, since=args.since, until=args.until)
    if args.command == "analytics" and args.analytics_command == "ai-ablation":
        return _run_analytics_ai_ablation(agent_root, since=args.since, until=args.until)
    if args.command == "analytics" and args.analytics_command == "snapshot":
        return _run_analytics_snapshot(agent_root, date=args.date)
    if args.command == "analytics" and args.analytics_command == "trend":
        return _run_analytics_trend(agent_root, since=args.since, until=args.until, output=args.output)
    if args.command == "analytics" and args.analytics_command == "weight-suggestion":
        return _run_analytics_weight_suggestion(agent_root, horizon=args.horizon, damping=args.damping)
    if args.command == "analytics" and args.analytics_command == "nightly-health":
        return _run_analytics_nightly_health(agent_root)
    if args.command == "analytics" and args.analytics_command == "thesis":
        return _run_analytics_thesis(agent_root, since=args.since, until=args.until)
    if args.command == "analytics" and args.analytics_command == "screen-eval":
        return _run_analytics_screen_eval(agent_root, since=args.since, until=args.until)
    if args.command == "analytics" and args.analytics_command == "setup-screen":
        return _run_analytics_setup_screen(
            agent_root,
            since=args.since,
            until=args.until,
            setups=args.setups,
            profile=args.profile,
            lookahead=args.lookahead,
            max_per_day=args.max_per_day,
            split_date=args.split_date,
        )
    if args.command == "analytics" and args.analytics_command == "discover":
        return _run_analytics_discover(agent_root, since=args.since, until=args.until, lookahead=args.lookahead, top_k=args.top_k)
    if args.command == "analytics" and args.analytics_command == "validate":
        return _run_analytics_validate(agent_root, since=args.since, until=args.until)
    if args.command == "analytics" and args.analytics_command == "retention":
        return _run_analytics_retention(agent_root, keep_days=args.keep_days, apply=args.apply)
    if args.command == "dashboard":
        return _run_dashboard(agent_root)
    if args.command == "screen":
        from trading_agent.screener.pipeline import run_screen

        return run_screen(agent_root, dry_run=args.dry_run, apply=True if args.apply else None)
    if args.command == "growth" and args.growth_command == "observe":
        return _run_growth_observe(agent_root, since=args.since, until=args.until)
    if args.command == "growth" and args.growth_command == "propose":
        return _run_growth_propose(agent_root, since=args.since, until=args.until)
    if args.command == "growth" and args.growth_command == "validate":
        return _run_growth_validate(agent_root, path=args.path)
    if args.command == "growth" and args.growth_command == "experiments":
        return _run_growth_experiments(agent_root, args)
    if args.command == "growth" and args.growth_command == "shadow":
        return _run_growth_shadow(agent_root, run_date=args.run_date)
    if args.command == "growth" and args.growth_command in {"evaluate", "recommend"}:
        return _run_growth_evaluate(agent_root, since=args.since, until=args.until, print_md=args.growth_command == "recommend")
    if args.command == "growth" and args.growth_command == "promote" and args.promote_command == "check":
        return _run_growth_promote_check(agent_root, experiment_id=args.experiment_id)
    return 0
