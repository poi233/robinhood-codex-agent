from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


OrderSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    previous_close: float | None = None
    timestamp: str = ""
    is_fresh: bool = True


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    average_cost: float
    market_price: float

    @property
    def unrealized_return(self) -> float:
        if self.average_cost <= 0:
            return 0.0
        return (self.market_price - self.average_cost) / self.average_cost


@dataclass(frozen=True)
class OpenOrder:
    symbol: str
    side: OrderSide
    quantity: float
    notional: float
    status: str = "open"


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: OrderSide
    order_type: Literal["limit"]
    limit_price: float
    estimated_notional: float
    quantity: float
    reference_price: float | None = None
    setup_type: str = ""
    stop_price: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    reward_risk: float | None = None
    reason_codes: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_json_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "time_in_force": "day",
            "setup_type": self.setup_type,
            "limit_price": self.limit_price,
            "estimated_notional": self.estimated_notional,
            "quantity": self.quantity,
            "reference_price": self.reference_price,
            "stop_price": self.stop_price,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "reward_risk": self.reward_risk,
            "reason_codes": list(self.reason_codes),
            "confidence": self.confidence,
        }


@dataclass
class PolicyInputs:
    run_date: str
    trading_mode: str
    risk_tier: int
    risk_caps: dict[str, Any] = field(default_factory=dict)
    universe: list[str] = field(default_factory=list)
    today_allowlist: list[str] = field(default_factory=list)
    daily_plan: dict[str, Any] | None = None
    dynamic_allowlist: dict[str, Any] = field(default_factory=dict)
    candidate_scores: dict[str, Any] = field(default_factory=dict)
    risk_overlay: dict[str, Any] = field(default_factory=dict)
    trader_watch_levels: dict[str, Any] = field(default_factory=dict)
    data_status_summary: dict[str, Any] = field(default_factory=dict)
    capital_snapshot: dict[str, Any] = field(default_factory=dict)
    catalyst_snapshot: dict[str, Any] = field(default_factory=dict)
    policy_profile: dict[str, Any] = field(default_factory=dict)
    daily_usage: dict[str, Any] = field(default_factory=dict)
    dsa_signals: dict[str, Any] = field(default_factory=dict)
    kronos_signals: dict[str, Any] = field(default_factory=dict)
    technical_signals: dict[str, Any] = field(default_factory=dict)
    research_reports: dict[str, Any] = field(default_factory=dict)
    account: dict[str, Any] = field(default_factory=dict)
    quotes: dict[str, Quote] = field(default_factory=dict)
    positions: dict[str, Position] = field(default_factory=dict)
    open_orders: list[OpenOrder] = field(default_factory=list)
    kill_switch_present: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    trading_mode: str
    checked_symbols: list[str]
    decision: str
    action_taken: str = "none"
    intent: OrderIntent | None = None
    reason: str = ""
    risk_checks: dict[str, bool | None] = field(default_factory=dict)
    blocked_reasons: list[str] = field(default_factory=list)

    def to_json_dict(self, *, timestamp: str) -> dict[str, object]:
        return {
            "timestamp": timestamp,
            "run_kind": "intraday",
            "trading_mode": self.trading_mode,
            "checked_symbols": list(self.checked_symbols),
            "decision": self.decision,
            "action_taken": self.action_taken,
            "proposed_order": self.intent.to_json_dict() if self.intent else None,
            "reason": self.reason,
            "risk_checks": dict(self.risk_checks),
            "blocked_reasons": list(self.blocked_reasons),
            "order_id_if_any": None,
        }
