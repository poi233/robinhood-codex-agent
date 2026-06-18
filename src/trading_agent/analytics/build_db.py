from __future__ import annotations

import sqlite3
from pathlib import Path

from trading_agent.analytics import loaders
from trading_agent.analytics.schema import INDEX_DDL, TABLE_DDL
from trading_agent.replay.analysis import discover_run_dates


def default_analytics_db_path(agent_root: Path) -> Path:
    return agent_root / "runtime" / "analytics" / "analytics.db"


def build_analytics_db(
    agent_root: Path,
    *,
    db_path: Path | None = None,
    since_date: str | None = None,
    until_date: str | None = None,
) -> dict[str, int]:
    """(Re)build analytics.db from runtime/state/runs/*.

    Idempotent: every call drops and recreates all 6 tables from the current
    JSON/JSONL source files, so rerunning never accumulates duplicate rows and
    always reflects the latest on-disk state.
    """
    db_path = db_path or default_analytics_db_path(agent_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    run_dates = discover_run_dates(agent_root, since_date=since_date, until_date=until_date)

    decisions_rows = loaders.load_decisions(agent_root, run_dates)
    table_rows: dict[str, list[dict[str, object]]] = {
        "runs": loaders.load_runs(agent_root, run_dates),
        "candidates": loaders.load_candidates(agent_root, run_dates),
        "decisions": decisions_rows,
        "orders": loaders.load_orders(agent_root, run_dates),
        "paper_equity": loaders.load_paper_equity(agent_root, run_dates),
        "blocked_reasons": loaders.load_blocked_reasons(decisions_rows),
        "intraday_rankings": loaders.load_intraday_rankings(agent_root, run_dates),
        "factor_alpha": loaders.load_factor_alpha(agent_root, run_dates),
        "regime_state": loaders.load_regime_state(agent_root, run_dates),
        "portfolio_target": loaders.load_portfolio_target(agent_root, run_dates),
    }

    connection = sqlite3.connect(db_path)
    try:
        for table_name in table_rows:
            connection.execute(f"DROP TABLE IF EXISTS {table_name}")
        for table_name, ddl in TABLE_DDL.items():
            connection.execute(ddl)
        for table_name, rows in table_rows.items():
            if not rows:
                continue
            columns = list(rows[0].keys())
            placeholders = ", ".join("?" for _ in columns)
            column_list = ", ".join(columns)
            connection.executemany(
                f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})",
                [tuple(row.get(column) for column in columns) for row in rows],
            )
        # N2: indexes (after tables; dropped implicitly when a table is dropped on rebuild).
        for index_ddl in INDEX_DDL:
            connection.execute(index_ddl)
        connection.commit()
    finally:
        connection.close()

    return {table_name: len(rows) for table_name, rows in table_rows.items()}
