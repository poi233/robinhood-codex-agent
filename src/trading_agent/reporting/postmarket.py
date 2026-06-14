from __future__ import annotations


def build_postmarket_archive_payload(run_date: str, summary: str) -> dict[str, object]:
    return {
        "date": run_date,
        "summary": summary,
    }
