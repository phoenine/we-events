from __future__ import annotations

from typing import Any

from core.articles.quality import build_content_quality_update


DEFAULT_RECLASSIFY_BATCH_SIZE = 100
MAX_RECLASSIFY_LIMIT = 5000
CONTENT_FETCH_STATUS_KEYS = ("failed", "fallback_required", "fetched")


async def reclassify_article_content_statuses(
    article_repo: Any,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    batch_size: int = DEFAULT_RECLASSIFY_BATCH_SIZE,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": 0,
        "updated": 0,
        "update_failed": 0,
        "items": [],
    }
    for status_key in CONTENT_FETCH_STATUS_KEYS:
        summary[status_key] = 0

    if limit is not None and (limit < 1 or limit > MAX_RECLASSIFY_LIMIT):
        raise ValueError(f"limit must be between 1 and {MAX_RECLASSIFY_LIMIT}")
    if batch_size < 1 or batch_size > MAX_RECLASSIFY_LIMIT:
        raise ValueError(f"batch_size must be between 1 and {MAX_RECLASSIFY_LIMIT}")

    offset = 0
    remaining = limit
    while remaining is None or remaining > 0:
        current_limit = batch_size if remaining is None else min(batch_size, remaining)
        articles = await article_repo.get_articles_base(limit=current_limit, offset=offset)
        if not articles:
            break

        summary["total"] += len(articles)
        for article in articles:
            article_id = str(article.get("id") or "")
            images = await article_repo.get_article_images(article_id) if article_id else []
            update = build_content_quality_update(article, image_count=len(images))
            status = update["content_fetch_status"]
            if status not in summary:
                summary[status] = 0
            summary[status] += 1

            item = {"id": article_id, **update}
            summary["items"].append(item)
            if dry_run or not article_id:
                continue
            try:
                await article_repo.update_article(article_id, update)
                summary["updated"] += 1
            except Exception as e:
                summary["update_failed"] += 1
                item["update_error"] = str(e)

        if len(articles) < current_limit:
            break
        offset += len(articles)
        if remaining is not None:
            remaining -= len(articles)

    return summary
