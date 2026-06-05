from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.activities import activity_repo, activity_run_repo
from core.activities.agent import PROMPT_VERSION, extract_activities_with_llm
from core.activities.extraction_input import build_activity_extraction_input
from core.activities.extraction_output import (
    ActivityExtractionOutput,
    ExtractedActivity,
    compute_event_status,
    compute_review_status,
    infer_start_at_from_event_text,
)
from core.articles import article_repo
from core.common.log import logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _activity_row(
    *,
    article: dict[str, Any],
    run_id: str,
    output: ActivityExtractionOutput,
    activity: ExtractedActivity,
) -> dict[str, Any]:
    raw_activity = activity.model_dump(mode="json")
    warnings = [str(item) for item in activity.warnings if str(item).strip()]
    start_at = activity.start_at or infer_start_at_from_event_text(
        activity.event_time_text,
        reference_timestamp=article.get("publish_time"),
    )
    end_at = activity.end_at
    event_status = compute_event_status(start_at, end_at)
    review_status = compute_review_status(output.confidence, warnings)

    return {
        "article_id": article.get("id") or "",
        "extraction_run_id": run_id,
        "source_wechat_account_id": article.get("wechat_account", {}).get("id") or None,
        "article_url": article.get("url") or "",
        "title": activity.title,
        "summary": activity.summary,
        "event_time_text": activity.event_time_text,
        "start_at": start_at,
        "end_at": end_at,
        "event_status": event_status,
        "location_text": activity.location_text,
        "registration_text": activity.registration_text,
        "registration_method": activity.registration_method,
        "registration_url": activity.registration_url,
        "qr_image_urls": activity.qr_image_urls,
        "fee_text": activity.fee_text,
        "audience": activity.audience,
        "review_status": review_status,
        "confidence": output.confidence,
        "evidence": [item.model_dump(mode="json") for item in activity.evidence],
        "warnings": warnings,
        "raw_activity": raw_activity,
        "created_at": _now(),
        "updated_at": _now(),
    }


async def extract_activities_from_article(article_id: str) -> dict[str, Any]:
    input_snapshot = await build_activity_extraction_input(article_id)
    article = input_snapshot["article"]
    text = (
        input_snapshot.get("content", {}).get("markdown")
        or input_snapshot.get("content", {}).get("text")
        or ""
    )
    if not str(text).strip():
        await article_repo.update_article(
            article_id,
            {
                "activity_extraction_status": "fallback_required",
                "activity_extraction_error": "文章正文为空，无法抽取活动",
            },
        )
        raise ValueError("文章正文为空，无法抽取活动")

    run = await activity_run_repo.create_run(
        {
            "article_id": article_id,
            "status": "processing",
            "model": "",
            "prompt_version": PROMPT_VERSION,
            "input_snapshot": input_snapshot,
            "started_at": _now(),
        }
    )
    run_id = run.get("id")
    if not run_id:
        raise RuntimeError("创建活动抽取记录失败")

    await article_repo.update_article(
        article_id,
        {
            "activity_extraction_status": "processing",
            "activity_extraction_error": "",
        },
    )

    try:
        output, raw_output_text, model = extract_activities_with_llm(input_snapshot)
        raw_output = output.model_dump(mode="json")

        if not output.is_activity_article:
            await activity_repo.delete_activities_by_article(article_id)
            await activity_run_repo.update_run(
                run_id,
                {
                    "status": "not_activity",
                    "model": model,
                    "raw_output": raw_output,
                    "raw_output_text": raw_output_text,
                    "finished_at": _now(),
                },
            )
            await article_repo.update_article(
                article_id,
                {
                    "activity_extraction_status": "not_activity",
                    "activity_extraction_error": output.reason,
                },
            )
            return {
                "run_id": run_id,
                "article_id": article_id,
                "article_status": "not_activity",
                "created_count": 0,
                "activities": [],
            }

        activity_rows = [
            _activity_row(article=article, run_id=run_id, output=output, activity=item)
            for item in output.activities
        ]
        if not activity_rows:
            raise ValueError("LLM 标记为活动文章，但未返回活动明细")

        await activity_repo.delete_activities_by_article(article_id)
        activities = await activity_repo.create_activities(activity_rows)
        await activity_run_repo.update_run(
            run_id,
            {
                "status": "success",
                "model": model,
                "raw_output": raw_output,
                "raw_output_text": raw_output_text,
                "finished_at": _now(),
            },
        )
        await article_repo.update_article(
            article_id,
            {
                "activity_extraction_status": "extracted",
                "activity_extraction_error": "",
            },
        )
        return {
            "run_id": run_id,
            "article_id": article_id,
            "article_status": "extracted",
            "created_count": len(activities),
            "activities": activities,
        }
    except Exception as exc:
        logger.exception(f"[activities.extract] failed article_id={article_id}: {exc}")
        await activity_run_repo.update_run(
            run_id,
            {
                "status": "failed",
                "error": str(exc),
                "finished_at": _now(),
            },
        )
        await article_repo.update_article(
            article_id,
            {
                "activity_extraction_status": "failed",
                "activity_extraction_error": str(exc),
            },
        )
        raise
