from __future__ import annotations

import time
from enum import StrEnum
from typing import Any


REPAIRABLE_CONTENT_FETCH_STATUSES = {"pending", "failed", "fallback_required"}


class ExistingArticleAction(StrEnum):
    COLLECT = "collect"
    REPAIR_CONTENT = "repair_content"
    SKIP = "skip"


def normalize_epoch_seconds(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        epoch = int(float(value))
    except (TypeError, ValueError):
        return None
    if epoch > 10_000_000_000:
        epoch = epoch // 1000
    return epoch if epoch > 0 else None


def item_publish_time(item: dict[str, Any]) -> int | None:
    return (
        normalize_epoch_seconds(item.get("publish_time"))
        or normalize_epoch_seconds(item.get("create_time"))
        or normalize_epoch_seconds(item.get("update_time"))
    )


def cutoff_timestamp(max_age_days: int | None) -> int | None:
    if max_age_days is None or int(max_age_days) <= 0:
        return None
    return int(time.time()) - int(max_age_days) * 24 * 60 * 60


def is_older_than_cutoff(item: dict[str, Any], cutoff_ts: int | None) -> bool:
    if cutoff_ts is None:
        return False
    publish_time = item_publish_time(item)
    return publish_time is not None and publish_time < cutoff_ts


def classify_existing_article_action(
    article: dict[str, Any] | None,
    *,
    repair_failed_existing: bool = True,
) -> ExistingArticleAction:
    if not article:
        return ExistingArticleAction.COLLECT
    if not repair_failed_existing:
        return ExistingArticleAction.SKIP

    content_status = str(article.get("content_fetch_status") or "pending").strip()
    if content_status in REPAIRABLE_CONTENT_FETCH_STATUSES:
        return ExistingArticleAction.REPAIR_CONTENT
    return ExistingArticleAction.SKIP


def classify_article_collection_decision(
    item: dict[str, Any],
    *,
    existing_article: dict[str, Any] | None,
    cutoff_ts: int | None,
    repair_failed_existing: bool = True,
) -> ExistingArticleAction:
    if is_older_than_cutoff(item, cutoff_ts):
        return ExistingArticleAction.SKIP
    return classify_existing_article_action(
        existing_article,
        repair_failed_existing=repair_failed_existing,
    )


def should_reset_activity_extraction_after_content_repair(
    existing_article: dict[str, Any] | None,
    new_article: dict[str, Any],
) -> bool:
    if not existing_article:
        return False
    previous_status = str(existing_article.get("content_fetch_status") or "pending").strip()
    new_status = str(new_article.get("content_fetch_status") or "pending").strip()
    return previous_status in REPAIRABLE_CONTENT_FETCH_STATUSES and new_status == "fetched"
