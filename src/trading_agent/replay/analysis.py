from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.context import build_runtime_paths


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


def _is_valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def discover_run_dates(agent_root: Path, *, since_date: str | None = None, until_date: str | None = None) -> list[str]:
    """Return sorted run-date strings found under runtime/state/runs/."""
    state_dir = agent_root / "runtime" / "state" / "runs"
    if not state_dir.exists():
        return []
    dates = sorted(p.name for p in state_dir.iterdir() if p.is_dir() and _is_valid_date(p.name))
    if since_date:
        dates = [d for d in dates if d >= since_date]
    if until_date:
        dates = [d for d in dates if d <= until_date]
    return dates


def _resolve_final_orders(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge per-order event streams into one final-state record per order_id."""
    initial: dict[str, dict[str, Any]] = {}
    follow_up: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        order_id = str(row.get("order_id") or "")
        if not order_id:
            continue
        if "event" not in row:
            initial[order_id] = row
        else:
            follow_up.setdefault(order_id, []).append(row)

    result: list[dict[str, Any]] = []
    for order_id, base in initial.items():
        final = dict(base)
        for event in sorted(follow_up.get(order_id, []), key=lambda e: str(e.get("timestamp") or "")):
            if event.get("status"):
                final["status"] = event["status"]
            if event.get("fill_price") is not None:
                final["fill_price"] = event["fill_price"]
        result.append(final)
    return result


def collect_paper_orders(agent_root: Path, *, run_dates: list[str]) -> list[dict[str, Any]]:
    """Collect final-state paper orders across multiple run dates."""
    all_orders: list[dict[str, Any]] = []
    for run_date in run_dates:
        path = build_runtime_paths(agent_root, run_date=run_date).paper_orders_log_path
        rows = _read_jsonl(path)
        for order in _resolve_final_orders(rows):
            order["_run_date"] = run_date
            all_orders.append(order)
    return all_orders


def collect_decisions(agent_root: Path, *, run_dates: list[str]) -> list[dict[str, Any]]:
    """Collect intraday policy decisions across multiple run dates."""
    all_decisions: list[dict[str, Any]] = []
    for run_date in run_dates:
        path = build_runtime_paths(agent_root, run_date=run_date).decisions_log_path
        for row in _read_jsonl(path):
            row["_run_date"] = run_date
            all_decisions.append(row)
    return all_decisions


def _status_canonical(status: str) -> str:
    s = status.lower()
    if s == "filled":
        return "filled"
    if s in {"pending", "open", "queued"}:
        return "pending"
    if s in {"pending_canceled", "canceled", "day_end_canceled"}:
        return "canceled"
    if s == "rejected":
        return "rejected"
    return "other"


def fill_rate_summary(orders: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate fill rate statistics from a list of resolved paper orders."""
    total = len(orders)
    if total == 0:
        return {
            "total_orders": 0,
            "filled": 0,
            "pending": 0,
            "canceled": 0,
            "rejected": 0,
            "fill_rate_pct": 0.0,
            "total_notional_submitted": 0.0,
            "filled_notional": 0.0,
            "by_symbol": {},
        }

    by_status: Counter[str] = Counter()
    by_symbol: dict[str, Counter[str]] = {}
    total_notional = 0.0
    filled_notional = 0.0

    for order in orders:
        canonical = _status_canonical(str(order.get("status") or ""))
        symbol = str(order.get("symbol") or "").upper()
        notional = float(order.get("notional") or 0)

        by_status[canonical] += 1
        total_notional += notional

        if canonical == "filled":
            qty = float(order.get("quantity") or 0)
            fp = float(order.get("fill_price") or order.get("limit_price") or 0)
            filled_notional += round(qty * fp, 2)

        if symbol:
            sym_ctr = by_symbol.setdefault(symbol, Counter())
            sym_ctr[canonical] += 1

    filled = by_status["filled"]
    fill_rate = round(filled / total * 100, 1) if total > 0 else 0.0

    # Sort symbols by filled count desc, then name asc
    by_symbol_sorted = dict(
        sorted(by_symbol.items(), key=lambda item: (-item[1]["filled"], item[0]))
    )

    return {
        "total_orders": total,
        "filled": filled,
        "pending": by_status["pending"],
        "canceled": by_status["canceled"],
        "rejected": by_status["rejected"],
        "fill_rate_pct": fill_rate,
        "total_notional_submitted": round(total_notional, 2),
        "filled_notional": round(filled_notional, 2),
        "by_symbol": {
            sym: {"filled": ctr["filled"], "total": sum(ctr.values())}
            for sym, ctr in by_symbol_sorted.items()
        },
    }


def blocked_reason_summary(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate blocked reason distribution from intraday policy decisions."""
    total = len(decisions)
    if total == 0:
        return {
            "total_evaluations": 0,
            "would_trade": 0,
            "no_trade": 0,
            "no_trade_rate_pct": 0.0,
            "reason_counts": {},
        }

    would_trade = sum(1 for d in decisions if d.get("decision") == "would_trade")
    no_trade = total - would_trade
    no_trade_rate = round(no_trade / total * 100, 1) if total > 0 else 0.0

    reason_counts: Counter[str] = Counter()
    for decision in decisions:
        for reason in decision.get("blocked_reasons") or []:
            if reason:
                reason_counts[str(reason)] += 1

    return {
        "total_evaluations": total,
        "would_trade": would_trade,
        "no_trade": no_trade,
        "no_trade_rate_pct": no_trade_rate,
        "reason_counts": dict(reason_counts.most_common()),
    }


def build_replay_report(
    agent_root: Path,
    *,
    since_date: str | None = None,
    until_date: str | None = None,
) -> dict[str, Any]:
    """Build the full local-computable replay report (fill rate + blocked reasons)."""
    run_dates = discover_run_dates(agent_root, since_date=since_date, until_date=until_date)
    if not run_dates:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": "no_run_dates_found",
            "run_dates": [],
            "run_date_count": 0,
            "fill_rate": fill_rate_summary([]),
            "blocked_reasons": blocked_reason_summary([]),
        }

    orders = collect_paper_orders(agent_root, run_dates=run_dates)
    decisions = collect_decisions(agent_root, run_dates=run_dates)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_dates": run_dates,
        "run_date_count": len(run_dates),
        "fill_rate": fill_rate_summary(orders),
        "blocked_reasons": blocked_reason_summary(decisions),
    }


def format_replay_report(report: dict[str, Any]) -> str:
    """Format a replay report as a human-readable string."""
    lines: list[str] = []
    run_dates = report.get("run_dates") or []
    period = f"{run_dates[0]} to {run_dates[-1]}" if len(run_dates) > 1 else (run_dates[0] if run_dates else "none")
    n = report.get("run_date_count", 0)
    date_label = f"{n} run date" + ("s" if n != 1 else "")

    lines.append("=== Paper Trading Replay Report ===")
    lines.append(f"Period:    {period}  ({date_label})")
    lines.append(f"Generated: {report.get('generated_at', '')}")

    if report.get("error"):
        lines.append("")
        lines.append(f"  No data found. Run the premarket + intraday pipeline first.")
        return "\n".join(lines)

    # Fill rate section
    fr = report.get("fill_rate") or {}
    total_orders = int(fr.get("total_orders") or 0)
    filled = int(fr.get("filled") or 0)
    pending = int(fr.get("pending") or 0)
    canceled = int(fr.get("canceled") or 0)
    rejected = int(fr.get("rejected") or 0)
    fill_rate = float(fr.get("fill_rate_pct") or 0)
    total_notional = float(fr.get("total_notional_submitted") or 0)
    filled_notional = float(fr.get("filled_notional") or 0)

    lines.append("")
    lines.append("--- Fill Rate (paper orders) ---")
    lines.append(f"  Total orders submitted:    {total_orders}")
    lines.append(f"    Filled:                  {filled}  ({fill_rate:.1f}%)")
    lines.append(f"    Pending (still open):    {pending}  ({_pct(pending, total_orders):.1f}%)")
    lines.append(f"    Canceled (day-end):      {canceled}  ({_pct(canceled, total_orders):.1f}%)")
    lines.append(f"    Rejected:                {rejected}  ({_pct(rejected, total_orders):.1f}%)")
    lines.append(f"  Total notional submitted:  ${total_notional:,.2f}")
    lines.append(f"  Filled notional:           ${filled_notional:,.2f}")

    by_symbol = fr.get("by_symbol") or {}
    if by_symbol:
        lines.append("")
        lines.append("  By symbol  (filled / submitted):")
        for sym, counts in list(by_symbol.items())[:10]:
            lines.append(f"    {sym:<10} {counts['filled']} / {counts['total']}")

    # Blocked reasons section
    br = report.get("blocked_reasons") or {}
    total_evals = int(br.get("total_evaluations") or 0)
    would_trade = int(br.get("would_trade") or 0)
    no_trade = int(br.get("no_trade") or 0)
    no_trade_rate = float(br.get("no_trade_rate_pct") or 0)
    reason_counts = br.get("reason_counts") or {}

    lines.append("")
    lines.append("--- Blocked Reason Distribution (intraday evaluations) ---")
    lines.append(f"  Total evaluations:         {total_evals}")
    lines.append(f"    Would-trade:             {would_trade}  ({_pct(would_trade, total_evals):.1f}%)")
    lines.append(f"    No-trade:                {no_trade}  ({no_trade_rate:.1f}%)")

    if reason_counts:
        lines.append("")
        lines.append("  Top blocked reasons:")
        for reason, count in list(reason_counts.items())[:15]:
            lines.append(f"    {reason:<40} {count}  ({_pct(count, total_evals):.1f}%)")
    elif total_evals > 0:
        lines.append("  (no blocked reasons recorded)")

    return "\n".join(lines)


def _pct(part: int | float, total: int | float) -> float:
    return round(part / total * 100, 1) if total > 0 else 0.0
