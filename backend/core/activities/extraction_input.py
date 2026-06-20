from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from core.articles import article_repo
from core.wechat_accounts import wechat_account_repo


def format_article_publish_date(
    value: Any,
    timezone_name: str = "Asia/Shanghai",
) -> str:
    if value in (None, ""):
        return ""

    tz = ZoneInfo(timezone_name)
    try:
        if isinstance(value, datetime):
            published_at = value
        elif isinstance(value, (int, float)) or str(value).strip().isdigit():
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            published_at = datetime.fromtimestamp(timestamp, tz)
        else:
            published_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        return published_at.astimezone(tz).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def html_to_text(html: str) -> str:
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text("\n", strip=True)
    except Exception:
        return str(html or "")


def build_image_contexts(article_text: str, images: list[dict[str, Any]]):
    # First version does not persist image context. Give each consecutive image
    # group a stable id and attach coarse article-level context.
    context = (article_text or "")[:500]
    grouped = []
    prev_position: int | None = None
    group_index = 0
    group_position = 0
    for image in images:
        try:
            position = int(image.get("position") or 0)
        except Exception:
            position = 0
        if prev_position is None or position != prev_position + 1:
            group_index += 1
            group_position = 1
        else:
            group_position += 1
        prev_position = position
        grouped.append(
            {
                "id": str(image.get("id") or ""),
                "position": position,
                "public_url": image.get("public_url") or "",
                "origin_url": image.get("origin_url") or "",
                "object_path": image.get("object_path") or "",
                "context_before": context,
                "context_after": "",
                "group_index": group_index,
                "group_position": group_position,
            }
        )
    return grouped


async def build_activity_extraction_input(article_id: str) -> dict[str, Any]:
    rows = await article_repo.get_articles_by_id(article_id)
    if not rows:
        raise ValueError("文章不存在")
    article = rows[0]

    account = None
    wechat_account_id = article.get("wechat_account_id")
    if wechat_account_id:
        account = await wechat_account_repo.get_wechat_account_by_id(wechat_account_id)

    markdown = str(article.get("content_md") or "").strip()
    text = markdown or html_to_text(str(article.get("content") or ""))
    images = await article_repo.get_article_images(article_id)
    publish_date = format_article_publish_date(article.get("publish_time"))

    return {
        "article": {
            "id": article.get("id"),
            "title": article.get("title") or "",
            "description": article.get("description") or "",
            "url": article.get("url") or "",
            "publish_time": article.get("publish_time"),
            "publish_date": publish_date,
            "wechat_account": {
                "id": wechat_account_id or "",
                "name": (account or {}).get("name") or "",
            },
        },
        "content": {
            "markdown": markdown,
            "text": text,
            "content_fetch_status": article.get("content_fetch_status") or "pending",
        },
        "images": build_image_contexts(text, images),
        "options": {
            "timezone": "Asia/Shanghai",
            "language": "zh-CN",
        },
    }
