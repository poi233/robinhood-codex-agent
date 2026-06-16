from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_experiment_paths
from trading_agent.core.io import write_json
from trading_agent.growth.experiment_queue import list_experiments
from trading_agent.growth.policy import load_growth_policy
from trading_agent.replay.analysis import build_replay_report, discover_run_dates

EVALUATED_STATES = {"active_shadow", "ready_for_review"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def collect_shadow_decisions(agent_root: Path, strategy_id: str, run_dates: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_date in run_dates:
        paths = build_experiment_paths(agent_root, run_date=run_date, strategy_id=strategy_id)
        for row in _read_jsonl(paths.shadow_decisions_log_path):
            row.setdefault("run_date", run_date)
            rows.append(row)
    return rows


def shadow_metrics(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(decisions)
    would_trade = sum(1 for d in decisions if d.get("decision") == "would_trade")
    reason_counts: Counter[str] = Counter()
    for decision in decisions:
        for reason in decision.get("blocked_reasons") or []:
            if reason:
                reason_counts[str(reason)] += 1
    shadow_days = len({str(d.get("run_date")) for d in decisions if d.get("run_date")})
    return {
        "total_evaluations": total,
        "would_trade": would_trade,
        "no_trade_rate_pct": round((total - would_trade) / total * 100, 1) if total else 0.0,
        "shadow_days": shadow_days,
        "reason_counts": dict(reason_counts.most_common()),
        # Not available until shadow order/equity simulation (deferred) and E1 forward returns land.
        "fill_rate_pct": None,
        "max_drawdown": None,
        "forward_returns": None,
    }


def _champion_metrics(agent_root: Path, *, since: str | None, until: str | None) -> dict[str, Any]:
    report = build_replay_report(agent_root, since_date=since, until_date=until)
    fill = report.get("fill_rate") or {}
    blocked = report.get("blocked_reasons") or {}
    return {
        "run_date_count": report.get("run_date_count", 0),
        "fill_rate_pct": fill.get("fill_rate_pct", 0.0),
        "filled": fill.get("filled", 0),
        "total_orders": fill.get("total_orders", 0),
        "no_trade_rate_pct": blocked.get("no_trade_rate_pct", 0.0),
        "total_evaluations": blocked.get("total_evaluations", 0),
        "reason_counts": blocked.get("reason_counts", {}),
    }


def _recommendation(metrics: dict[str, Any], champion: dict[str, Any], promotion_rules: dict[str, Any]) -> dict[str, Any]:
    """Decide whether to RECOMMEND a challenger for human review. Never auto-promotes.

    Any unmet rule, or any required metric that isn't available yet (challenger fill
    rate / drawdown need shadow order+equity simulation; forward returns need E1), is a
    blocking reason — so until that data exists the recommendation stays False.
    """
    reasons: list[str] = []

    min_shadow_days = int(promotion_rules.get("min_shadow_days", 0) or 0)
    if metrics["shadow_days"] < min_shadow_days:
        reasons.append(f"min_shadow_days_not_met: {metrics['shadow_days']} < {min_shadow_days}")

    if promotion_rules.get("fill_rate_not_worse_than_champion"):
        if metrics.get("fill_rate_pct") is None:
            reasons.append("fill_rate_unavailable: shadow order simulation not implemented yet (G6 is decisions-only)")
        elif metrics["fill_rate_pct"] < float(champion.get("fill_rate_pct") or 0):
            reasons.append("fill_rate_worse_than_champion")

    if promotion_rules.get("max_drawdown_not_worse_than_champion"):
        if metrics.get("max_drawdown") is None:
            reasons.append("max_drawdown_unavailable: shadow equity curve not simulated yet")

    return {
        "recommend_promote": not reasons,
        "requires_human_final_approval": bool(promotion_rules.get("require_human_final_approval", True)),
        "blocking_reasons": reasons,
    }


def evaluate_experiments(agent_root: Path, *, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    champion = _champion_metrics(agent_root, since=since, until=until)
    policy = load_growth_policy(agent_root)
    promotion_rules = policy.get("promotion_rules") or {}

    challengers: list[dict[str, Any]] = []
    for experiment in list_experiments(agent_root):
        if experiment.get("status") not in EVALUATED_STATES:
            continue
        strategy_id = str(experiment.get("challenger_strategy_id") or experiment.get("experiment_id"))
        decisions = collect_shadow_decisions(agent_root, strategy_id, run_dates)
        metrics = shadow_metrics(decisions)
        challengers.append({
            "experiment_id": experiment.get("experiment_id"),
            "challenger_strategy_id": strategy_id,
            "parent_strategy_id": experiment.get("parent_strategy_id"),
            "status": experiment.get("status"),
            "metrics": metrics,
            "recommendation": _recommendation(metrics, champion, promotion_rules),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_date_range": {"since": since, "until": until},
        "champion": champion,
        "challengers": challengers,
    }


def default_experiment_report_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "experiment_report.json"


def default_recommendation_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "promotion_recommendation.md"


def _recommendation_markdown(report: dict[str, Any]) -> str:
    champion = report["champion"]
    lines = [
        "# Promotion Recommendation",
        "",
        f"_Generated {report['generated_at']}._ Recommend-only — promotion is always a manual YAML edit (G8).",
        "",
        "## Champion",
        "",
        f"- Trading days: {champion['run_date_count']}  ·  fill rate: {champion['fill_rate_pct']}%  ·  "
        f"no-trade rate: {champion['no_trade_rate_pct']}%  ·  orders: {champion['total_orders']}",
        "",
        "## Challengers",
        "",
    ]
    if not report["challengers"]:
        lines.append("_No active_shadow / ready_for_review experiments to evaluate._")
        return "\n".join(lines) + "\n"
    for chal in report["challengers"]:
        m = chal["metrics"]
        rec = chal["recommendation"]
        verdict = "✅ eligible for human review" if rec["recommend_promote"] else "⛔ not recommended"
        lines.append(f"### {chal['challenger_strategy_id']}  ({chal['status']})")
        lines.append("")
        lines.append(f"- Shadow days: {m['shadow_days']}  ·  evaluations: {m['total_evaluations']}  ·  "
                     f"would-trade: {m['would_trade']}  ·  no-trade rate: {m['no_trade_rate_pct']}%")
        lines.append(f"- Verdict: **{verdict}**")
        if rec["blocking_reasons"]:
            lines.append("- Blocking reasons:")
            lines.extend(f"  - {reason}" for reason in rec["blocking_reasons"])
        lines.append("")
    return "\n".join(lines) + "\n"


def write_experiment_report(agent_root: Path, *, since: str | None = None, until: str | None = None) -> tuple[Path, Path]:
    report = evaluate_experiments(agent_root, since=since, until=until)
    json_path = default_experiment_report_path(agent_root)
    md_path = default_recommendation_md_path(agent_root)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_recommendation_markdown(report), encoding="utf-8")
    return json_path, md_path
