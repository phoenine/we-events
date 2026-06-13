from __future__ import annotations

from typing import Any

from core.articles.quality import build_content_quality_update


async def reclassify_article_content_statuses(
    article_repo: Any,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    articles = await article_repo.get_articles_base(limit=limit)
    summary: dict[str, Any] = {
        "total": len(articles),
        "updated": 0,
        "failed": 0,
        "fallback_required": 0,
        "fetched": 0,
        "items": [],
    }

    for article in articles:
        article_id = str(article.get("id") or "")
        images = await article_repo.get_article_images(article_id) if article_id else []
        update = build_content_quality_update(article, image_count=len(images))
        status = update["content_fetch_status"]
        if status in summary:
            summary[status] += 1
        summary["items"].append({"id": article_id, **update})
        if dry_run or not article_id:
            continue
        await article_repo.update_article(article_id, update)
        summary["updated"] += 1

    return summary
