from __future__ import annotations

from datetime import datetime
from typing import Any

from trading_agent.core.time import PT


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _paper_buying_power(paper_account: dict[str, Any] | None, paper_starting_cash: float) -> tuple[float, str]:
    if isinstance(paper_account, dict):
        cash = _as_float(paper_account.get("cash"))
        if cash is not None:
            return cash, "paper_account"
        buying_power = _as_float(paper_account.get("buying_power"))
        if buying_power is not None:
            return buying_power, "paper_account"
    return round(float(paper_starting_cash), 2), "paper_starting_cash"


def resolve_buying_power(
    *,
    trading_mode: str,
    paper_account: dict[str, Any] | None,
    account_snapshot: dict[str, Any] | None,
    paper_starting_cash: float,
) -> dict[str, Any]:
    mode = (trading_mode or "paper").lower()
    real_account_buying_power = _as_float((account_snapshot or {}).get("buying_power"))
    paper_buying_power, paper_source = _paper_buying_power(paper_account, paper_starting_cash)

    if mode == "paper":
        return {
            "trading_mode": mode,
            "buying_power": paper_buying_power,
            "source": paper_source,
            "paper_buying_power": paper_buying_power,
            "real_account_buying_power": real_account_buying_power,
        }

    return {
        "trading_mode": mode,
        "buying_power": real_account_buying_power,
        "source": "robinhood_account_snapshot" if real_account_buying_power is not None else "missing_robinhood_account_snapshot",
        "paper_buying_power": paper_buying_power,
        "real_account_buying_power": real_account_buying_power,
    }


def build_capital_snapshot(
    *,
    run_date: str,
    trading_mode: str,
    paper_account: dict[str, Any] | None,
    account_snapshot: dict[str, Any] | None,
    paper_starting_cash: float,
) -> dict[str, Any]:
    resolved = resolve_buying_power(
        trading_mode=trading_mode,
        paper_account=paper_account,
        account_snapshot=account_snapshot,
        paper_starting_cash=paper_starting_cash,
    )
    return {
        "date": run_date,
        "generated_at": datetime.now(tz=PT).isoformat(),
        "trading_mode": resolved["trading_mode"],
        "sizing_buying_power": resolved["buying_power"],
        "sizing_source": resolved["source"],
        "paper_buying_power": resolved["paper_buying_power"],
        "real_account_buying_power": resolved["real_account_buying_power"],
        "notes": (
            "Paper mode uses local paper ledger cash for sizing; Robinhood buying power remains "
            "a read-only real-account reference."
            if resolved["trading_mode"] == "paper"
            else "Review/live modes use Robinhood account snapshot buying power for sizing."
        ),
    }

