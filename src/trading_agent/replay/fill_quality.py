from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.core.io import write_json
from trading_agent.replay.analysis import collect_paper_orders, discover_run_dates

# Conservative spread assumptions (round-trip, bps) the report stress-tests the paper edge against.
# The paper fill model is optimistic (fills near the reference/last price); a real limit order pays
# roughly half the spread per side, so these scenarios quantify "how much edge is the optimism worth".
DEFAULT_SPREAD_SCENARIOS_BPS = (5.0, 10.0, 25.0, 50.0)

_FILLED_STATUSES = {"filled", "partial_filled"}


@dataclass
class Fill:
    run_date: str
    symbol: str
    side: str
    quantity: float
    reference_price: float
    fill_price: float
    notional: float
    spread_bps: float | None  # captured top-of-book spread, None on the bookless daily feed

    @property
    def realized_slippage_bps(self) -> float | None:
        """Signed fill cost vs the reference (last) price, bps, positive = worse for us."""
        if self.reference_price <= 0:
            return None
        raw = (self.fill_price - self.reference_price) / self.reference_price
        signed = raw if self.side == "buy" else -raw
        return signed * 10000.0


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_fills(agent_root: Path, *, since: str | None = None, until: str | None = None) -> list[Fill]:
    """Final-state filled paper orders across run dates, as Fill rows. Skips orders missing a fill
    price or a reference price (can't measure quality without both)."""
    run_dates = discover_run_dates(agent_root, since_date=since, until_date=until)
    if not run_dates:
        return []
    fills: list[Fill] = []
    for order in collect_paper_orders(agent_root, run_dates=run_dates):
        status = str(order.get("status") or "").lower()
        if status not in _FILLED_STATUSES:
            continue
        side = str(order.get("side") or "").lower()
        if side not in {"buy", "sell"}:
            continue
        fill_price = _as_float(order.get("fill_price"))
        reference_price = _as_float(order.get("current_price_at_submit"))
        if fill_price is None or fill_price <= 0 or reference_price is None or reference_price <= 0:
            continue
        quantity = _as_float(order.get("filled_qty"))
        if quantity is None or quantity <= 0:
            quantity = _as_float(order.get("quantity")) or 0.0
        fills.append(Fill(
            run_date=str(order.get("_run_date") or order.get("timestamp") or "")[:10],
            symbol=str(order.get("symbol") or "").upper(),
            side=side,
            quantity=quantity,
            reference_price=reference_price,
            fill_price=fill_price,
            notional=round(quantity * fill_price, 2),
            spread_bps=_as_float(order.get("spread_bps")),
        ))
    return fills


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _slippage_bucket(slippage_bps: float) -> str:
    """Realized-slippage liquidity proxy, used when no captured spread is available."""
    s = abs(slippage_bps)
    if s < 5:
        return "tight (<5bps)"
    if s < 15:
        return "normal (5-15bps)"
    if s < 40:
        return "wide (15-40bps)"
    return "very wide (>=40bps)"


def fill_quality_report(
    agent_root: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    spread_scenarios_bps: tuple[float, ...] = DEFAULT_SPREAD_SCENARIOS_BPS,
) -> dict[str, Any]:
    """E4 fill-quality report. Read-only; does not change any fill behavior.

    - Realized slippage: fill_price vs reference, the optimism already baked into paper fills.
    - Buckets: mean realized slippage grouped by captured spread (when a book exists) or by a
      realized-slippage liquidity proxy otherwise.
    - Conservative scenarios: for each assumed round-trip spread, the per-side fill cost and the
      estimated round-trip edge haircut (≈ full assumed spread), plus the dollar drag on the total
      filled notional. This is the direct answer to "if fills were conservative, how much edge
      would the calibration lose?"."""
    fills = load_fills(agent_root, since=since, until=until)
    generated_at = datetime.now(timezone.utc).isoformat()

    if not fills:
        return {
            "generated_at": generated_at,
            "fill_count": 0,
            "scenarios": [],
            "buckets": [],
            "note": "No filled paper orders with reference + fill prices yet.",
        }

    buy_slip = [f.realized_slippage_bps for f in fills if f.side == "buy" and f.realized_slippage_bps is not None]
    sell_slip = [f.realized_slippage_bps for f in fills if f.side == "sell" and f.realized_slippage_bps is not None]
    all_slip = [f.realized_slippage_bps for f in fills if f.realized_slippage_bps is not None]
    with_book = [f for f in fills if f.spread_bps is not None]
    total_notional = round(sum(f.notional for f in fills), 2)

    # Bucketing: prefer captured spread; fall back to the realized-slippage proxy.
    use_book = len(with_book) >= max(3, len(fills) // 2)
    grouped: dict[str, list[float]] = {}
    for f in fills:
        slip = f.realized_slippage_bps
        if slip is None:
            continue
        if use_book and f.spread_bps is not None:
            sb = f.spread_bps
            label = "tight (<10bps)" if sb < 10 else "normal (10-30bps)" if sb < 30 else "wide (>=30bps)"
        else:
            label = _slippage_bucket(slip)
        grouped.setdefault(label, []).append(slip)
    buckets = [
        {"bucket": label, "count": len(vals), "mean_slippage_bps": _mean(vals)}
        for label, vals in sorted(grouped.items())
    ]

    scenarios = []
    for spread in spread_scenarios_bps:
        half = spread / 2.0
        # Extra per-side cost beyond the optimistic fill = half-spread minus whatever the paper model
        # already charged (mean realized slippage); never negative.
        realized_mean = _mean(all_slip) or 0.0
        extra_per_side = max(0.0, half - realized_mean)
        roundtrip_haircut = round(spread, 4)  # buy half + sell half, before crediting realized cost
        dollar_drag = round(total_notional * (roundtrip_haircut / 10000.0), 2)
        scenarios.append({
            "assumed_spread_bps": round(spread, 4),
            "per_side_cost_bps": round(half, 4),
            "extra_vs_realized_per_side_bps": round(extra_per_side, 4),
            "roundtrip_edge_haircut_bps": roundtrip_haircut,
            "dollar_drag_on_filled_notional": dollar_drag,
        })

    return {
        "generated_at": generated_at,
        "fill_count": len(fills),
        "buy_count": len(buy_slip),
        "sell_count": len(sell_slip),
        "captured_book_count": len(with_book),
        "total_filled_notional": total_notional,
        "mean_realized_slippage_bps": _mean(all_slip),
        "mean_realized_slippage_buy_bps": _mean(buy_slip),
        "mean_realized_slippage_sell_bps": _mean(sell_slip),
        "mean_captured_spread_bps": _mean([f.spread_bps for f in with_book]) if with_book else None,
        "bucket_basis": "captured_spread" if use_book else "realized_slippage_proxy",
        "buckets": buckets,
        "scenarios": scenarios,
    }


def default_fill_quality_report_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "fill_quality_report.json"


def default_fill_quality_md_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "fill_quality_report.md"


def _fmt_bps(value: Any) -> str:
    return f"{value:+.2f}bps" if isinstance(value, (int, float)) else "—"


def format_fill_quality_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Fill Quality Report (E4)",
        "",
        f"_Generated {report['generated_at']}._ Filled paper orders: {report['fill_count']}",
        "",
        "> Read-only. Does not change the paper fill model. Quantifies how optimistic paper fills are "
        "and how much calibration edge would shrink under conservative (spread-aware) fills.",
        "",
    ]
    if report["fill_count"] == 0:
        lines.append(f"_{report.get('note', 'No fills yet.')}_")
        return "\n".join(lines) + "\n"

    lines.append("## Realized slippage (fill vs reference price)")
    lines.append("")
    lines.append(f"- all: {_fmt_bps(report['mean_realized_slippage_bps'])}  ·  "
                 f"buy: {_fmt_bps(report['mean_realized_slippage_buy_bps'])}  ·  "
                 f"sell: {_fmt_bps(report['mean_realized_slippage_sell_bps'])}")
    if report.get("mean_captured_spread_bps") is not None:
        lines.append(f"- captured book on {report['captured_book_count']}/{report['fill_count']} fills; "
                     f"mean captured spread: {_fmt_bps(report['mean_captured_spread_bps'])}")
    else:
        lines.append("- no top-of-book captured (daily feed has no bid/ask); buckets use the "
                     "realized-slippage liquidity proxy.")
    lines.append("")

    lines.append(f"## Slippage by bucket (basis: {report['bucket_basis']})")
    lines.append("")
    for b in report["buckets"]:
        lines.append(f"- {b['bucket']}: n={b['count']}  mean={_fmt_bps(b['mean_slippage_bps'])}")
    lines.append("")

    lines.append("## Conservative-fill sensitivity (optimistic vs conservative)")
    lines.append("")
    lines.append("_Round-trip edge haircut ≈ the full assumed spread; dollar drag is on total filled "
                 "notional. If your paper edge per round-trip is smaller than the haircut, the edge is "
                 "an artifact of optimistic fills._")
    lines.append(f"_Total filled notional: ${report['total_filled_notional']:,.0f}._")
    for s in report["scenarios"]:
        lines.append(f"- spread {s['assumed_spread_bps']:.0f}bps → per-side {s['per_side_cost_bps']:.1f}bps  "
                     f"(extra vs realized {s['extra_vs_realized_per_side_bps']:.1f}bps)  ·  "
                     f"round-trip haircut {s['roundtrip_edge_haircut_bps']:.0f}bps  ·  "
                     f"drag ${s['dollar_drag_on_filled_notional']:,.0f}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_fill_quality_report(
    agent_root: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    spread_scenarios_bps: tuple[float, ...] = DEFAULT_SPREAD_SCENARIOS_BPS,
) -> tuple[Path, Path]:
    report = fill_quality_report(agent_root, since=since, until=until, spread_scenarios_bps=spread_scenarios_bps)
    json_path = default_fill_quality_report_path(agent_root)
    md_path = default_fill_quality_md_path(agent_root)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(format_fill_quality_markdown(report), encoding="utf-8")
    return json_path, md_path
