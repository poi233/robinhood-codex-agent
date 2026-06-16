from __future__ import annotations

TABLE_DDL: dict[str, str] = {
    "runs": """
        CREATE TABLE runs (
            run_date TEXT PRIMARY KEY,
            strategy_id TEXT,
            git_commit TEXT,
            config_hash TEXT,
            trading_mode TEXT,
            effective_risk_tier INTEGER
        )
    """,
    "candidates": """
        CREATE TABLE candidates (
            run_date TEXT,
            symbol TEXT,
            candidate_score REAL,
            score_status TEXT,
            technical_score REAL,
            catalyst_score REAL,
            dsa_score REAL,
            kronos_score REAL,
            quote_score REAL,
            is_watchlist INTEGER,
            is_tradable INTEGER
        )
    """,
    "decisions": """
        CREATE TABLE decisions (
            timestamp TEXT,
            run_date TEXT,
            decision TEXT,
            symbol TEXT,
            side TEXT,
            setup_type TEXT,
            blocked_reasons TEXT,
            confidence REAL
        )
    """,
    "orders": """
        CREATE TABLE orders (
            timestamp TEXT,
            run_date TEXT,
            order_id TEXT,
            symbol TEXT,
            side TEXT,
            status TEXT,
            quantity REAL,
            limit_price REAL,
            fill_price REAL,
            notional REAL,
            reason_codes TEXT
        )
    """,
    "paper_equity": """
        CREATE TABLE paper_equity (
            timestamp TEXT,
            run_date TEXT,
            event TEXT,
            cash REAL,
            positions_market_value REAL,
            total_equity REAL,
            realized_pnl REAL
        )
    """,
    "blocked_reasons": """
        CREATE TABLE blocked_reasons (
            run_date TEXT,
            reason TEXT,
            count INTEGER
        )
    """,
}
