from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.growth.evaluator import evaluate_experiments
from trading_agent.growth.experiment_queue import load_experiments
from trading_agent.strategy.registry import load_active_strategy

# A challenger can only be *considered* for promotion once a human has moved it to
# ready_for_review (after watching the shadow run) AND the evaluator recommends it.
PROMOTABLE_STATUS = "ready_for_review"


def _changelog_draft(experiment: dict[str, Any], champion: dict[str, Any], today: str) -> str:
    challenger_id = experiment.get("challenger_strategy_id")
    parent = experiment.get("parent_strategy_id") or champion.get("strategy_id")
    field = experiment.get("field")
    current = experiment.get("current")
    proposed = experiment.get("proposed")
    return "\n".join([
        f"## {challenger_id}",
        "",
        f"- **Parent**: {parent}",
        f"- **Date**: {today}",
        "- **Commit**: `<fill-in-after-commit>`",
        f"- **Config**: same as `{parent}` except `{experiment.get('module')}.{field}` "
        f"`{current}` → `{proposed}`",
        f"- **Change reason**: Shadow experiment `{experiment.get('experiment_id')}` "
        f"(proposal `{experiment.get('proposal_id')}`) moved `{field}` from `{current}` to "
        f"`{proposed}` and was reviewed in shadow paper. Promote only after a human edits "
        "`strategy_registry.yaml`.",
        "",
    ])


def _registry_entry_draft(experiment: dict[str, Any], champion: dict[str, Any]) -> str:
    challenger_id = experiment.get("challenger_strategy_id")
    parent = experiment.get("parent_strategy_id") or champion.get("strategy_id")
    return "\n".join([
        f"  {challenger_id}:",
        "    status: candidate",
        f"    scoring_profile: {champion.get('scoring_profile')}",
        f"    policy_profile: {champion.get('policy_profile')}",
        f"    watchlist: {champion.get('watchlist')}",
        f"    risk_tier_paper: {champion.get('risk_tier_paper')}",
        f"    risk_tier_live: {champion.get('risk_tier_live')}",
        f"    parent: {parent}",
        f"    change_reason: \"shadow experiment {experiment.get('experiment_id')}: "
        f"{experiment.get('module')}.{experiment.get('field')} "
        f"{experiment.get('current')} -> {experiment.get('proposed')}\"",
        "",
        "  # NOTE: a numeric scoring override is not a named profile. To materialize it you",
        "  # must either add a new scoring profile carrying the changed value or extend the",
        "  # registry with per-strategy overrides, then point active_strategy at it BY HAND.",
    ])


def build_promotion_check(agent_root: Path, experiment_id: str) -> dict[str, Any]:
    """Validate a challenger for promotion and produce drafts. NEVER edits the registry.

    Returns the experiment, the evaluator recommendation, eligibility (ready_for_review +
    recommended), blocking reasons, and ready-to-paste changelog / registry drafts. The
    actual promotion stays a manual strategy_registry.yaml edit by a human (G8 red line).
    """
    experiments = load_experiments(agent_root)
    if experiment_id not in experiments:
        raise KeyError(experiment_id)
    experiment = {"experiment_id": experiment_id, **experiments[experiment_id]}

    report = evaluate_experiments(agent_root)
    challenger_id = experiment.get("challenger_strategy_id")
    verdict = next(
        (c["recommendation"] for c in report["challengers"] if c["challenger_strategy_id"] == challenger_id),
        {"recommend_promote": False, "blocking_reasons": ["challenger_not_evaluated (not active_shadow/ready_for_review)"]},
    )

    blocking_reasons: list[str] = []
    if experiment.get("status") != PROMOTABLE_STATUS:
        blocking_reasons.append(f"experiment status {experiment.get('status')!r} is not ready_for_review")
    if not verdict.get("recommend_promote"):
        blocking_reasons.extend(verdict.get("blocking_reasons") or ["not recommended by evaluator"])

    champion = load_active_strategy(agent_root)
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "experiment_id": experiment_id,
        "challenger_strategy_id": challenger_id,
        "eligible": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "recommendation": verdict,
        "changelog_draft": _changelog_draft(experiment, champion, today),
        "registry_entry_draft": _registry_entry_draft(experiment, champion),
    }


def _promotion_markdown(check: dict[str, Any]) -> str:
    verdict = "✅ ELIGIBLE for human promotion" if check["eligible"] else "⛔ NOT eligible"
    lines = [
        f"# Promotion check — {check['challenger_strategy_id']}",
        "",
        f"Experiment: `{check['experiment_id']}`  ·  Verdict: **{verdict}**",
        "",
        "> This command never edits `strategy_registry.yaml`. Promotion is a manual edit by a human.",
        "",
    ]
    if check["blocking_reasons"]:
        lines.append("## Blocking reasons")
        lines.append("")
        lines.extend(f"- {reason}" for reason in check["blocking_reasons"])
        lines.append("")
    lines += [
        "## Changelog draft",
        "",
        "Paste into `docs/strategy-changelog.md`:",
        "",
        "```markdown",
        check["changelog_draft"].rstrip(),
        "```",
        "",
        "## strategy_registry.yaml entry draft",
        "",
        "Paste under `strategies:` and set `active_strategy:` BY HAND when you decide to promote:",
        "",
        "```yaml",
        check["registry_entry_draft"].rstrip(),
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def default_promotion_draft_path(agent_root: Path, experiment_id: str) -> Path:
    return agent_root / "runtime" / "analytics" / "promotion_drafts" / f"{experiment_id}.md"


def write_promotion_check(agent_root: Path, experiment_id: str) -> Path:
    check = build_promotion_check(agent_root, experiment_id)
    out_path = default_promotion_draft_path(agent_root, experiment_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_promotion_markdown(check), encoding="utf-8")
    return out_path
