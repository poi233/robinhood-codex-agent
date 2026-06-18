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
            confidence REAL,
            per_candidate_blocks TEXT,
            advisory_overlay TEXT,
            thesis_tags TEXT
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
            reason_codes TEXT,
            setup_type TEXT,
            stop_price REAL,
            target_1 REAL,
            target_2 REAL,
            reward_risk REAL,
            confidence REAL,
            bid REAL,
            ask REAL,
            mid_price REAL,
            spread_bps REAL,
            slippage_bps REAL
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
    "intraday_rankings": """
        CREATE TABLE intraday_rankings (
            timestamp TEXT,
            run_date TEXT,
            symbol TEXT,
            trade_readiness_score REAL,
            base_trade_readiness_score REAL,
            advisory_rank_delta REAL,
            price_setup_score REAL,
            candidate_score REAL,
            technical_score REAL,
            research_score REAL,
            catalyst_score REAL,
            liquidity_score REAL,
            advisory_overlay TEXT
        )
    """,
    # N1: H2 factor_alpha layer — one row per (run_date, symbol) so factor scores can be joined to
    # forward returns / candidate scores in SQL instead of only via per-run JSON.
    "factor_alpha": """
        CREATE TABLE factor_alpha (
            run_date TEXT,
            symbol TEXT,
            factor_alpha_score REAL,
            risk_flags TEXT,
            factor_components TEXT
        )
    """,
    # N1: K2 regime engine — one row per run_date.
    "regime_state": """
        CREATE TABLE regime_state (
            run_date TEXT PRIMARY KEY,
            regime TEXT,
            multiplier REAL,
            applied_multiplier REAL,
            vix REAL,
            spy_return_20d REAL,
            spy_above_sma200 INTEGER,
            reasons TEXT
        )
    """,
    # N1: K1 portfolio target — one row per run_date (scalars); exposures/breaches as JSON.
    "portfolio_target": """
        CREATE TABLE portfolio_target (
            run_date TEXT PRIMARY KEY,
            total_equity REAL,
            cash REAL,
            cash_weight REAL,
            theme_exposure TEXT,
            sector_exposure TEXT,
            breaches TEXT
        )
    """,
}

# N2: indexes on the columns dashboards / calibration filter and sort by. Built after the tables in
# build_db (and dropped implicitly when the table is dropped on rebuild), so they need no migration.
INDEX_DDL: list[str] = [
    "CREATE INDEX idx_candidates_run_date ON candidates(run_date)",
    "CREATE INDEX idx_decisions_run_date ON decisions(run_date)",
    "CREATE INDEX idx_orders_run_date_status ON orders(run_date, status)",
    "CREATE INDEX idx_intraday_rankings_run_date_symbol ON intraday_rankings(run_date, symbol)",
    "CREATE INDEX idx_paper_equity_run_date_ts ON paper_equity(run_date, timestamp)",
    "CREATE INDEX idx_blocked_reasons_run_date ON blocked_reasons(run_date)",
    "CREATE INDEX idx_factor_alpha_run_date_symbol ON factor_alpha(run_date, symbol)",
]
