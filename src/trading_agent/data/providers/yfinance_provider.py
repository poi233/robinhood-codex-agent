from __future__ import annotations

from typing import Any


def jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    return value


def extract_url(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("url")
    return None


def normalize_news_item(item: dict[str, Any]) -> dict[str, object] | None:
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    title = content.get("title") or item.get("title")
    if not title:
        return None

    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    return {
        "title": title,
        "source": provider.get("displayName") or provider.get("name") or "yfinance",
        "published_at": content.get("pubDate") or content.get("displayTime") or item.get("providerPublishTime"),
        "url": extract_url(content.get("clickThroughUrl")) or extract_url(content.get("canonicalUrl")),
    }
