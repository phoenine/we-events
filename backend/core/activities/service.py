import os
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from core.activities import activity_repo
from core.common.log import logger


async def upsert_activity_from_article(
    article: Dict[str, Any], analysis: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool]:
    """从文章中提取的活动信息进行创建或更新。"""
    existing_activities = await activity_repo.get_activities(
        article_id=article["id"], limit=1, offset=0
    )

    now = datetime.now(timezone.utc)
    activity_data = {
        "title": analysis.get("registration_title", "无"),
        "original_title": article.get("title") or "",
        "source_wechat_account_id": article.get("wechat_account_id"),
        "registration_time_text": analysis.get("registration_time", "即时"),
        "registration_method": analysis.get(
            "registration_method", article.get("url") or "无"
        ),
        "event_time_text": analysis.get("event_time", "无"),
        "event_fee": analysis.get("event_fee", "无"),
        "audience": analysis.get("audience", "无"),
        "article_url": article.get("url") or "无",
        "status": "active",
        "extraction_status": "extracted",
        "extracted_by": "llm",
        "extraction_model": os.getenv("LLM_MODEL", "Qwen/Qwen3-32B"),
        "extraction_raw": analysis,
        "updated_at": now.isoformat(),
    }

    if existing_activities:
        existing = existing_activities[0]
        logger.info(f"[activities.upsert] update article_id={article['id']}")
        updated_activities = await activity_repo.update_activity(
            existing["id"], activity_data
        )
        logger.debug(
            "[activities.upsert] update fields "
            f"registration_time_text={activity_data['registration_time_text']!r}, "
            f"registration_method={activity_data['registration_method']!r}, "
            f"event_time_text={activity_data['event_time_text']!r}, "
            f"event_fee={activity_data['event_fee']!r}, "
            f"audience={activity_data['audience']!r}, "
            f"updated_at={activity_data['updated_at']}"
        )
        return updated_activities[0] if updated_activities else existing, False

    logger.info(f"[activities.upsert] create article_id={article['id']}")
    activity_data["article_id"] = article["id"]
    activity_data["created_at"] = now.isoformat()
    created_activity = await activity_repo.create_activity(activity_data)
    logger.debug(
        "[activities.upsert] create fields "
        f"registration_time_text={activity_data['registration_time_text']!r}, "
        f"registration_method={activity_data['registration_method']!r}, "
        f"event_time_text={activity_data['event_time_text']!r}, "
        f"event_fee={activity_data['event_fee']!r}, "
        f"audience={activity_data['audience']!r}, "
        f"created_at={activity_data['created_at']}, updated_at={activity_data['updated_at']}"
    )
    return created_activity, True
