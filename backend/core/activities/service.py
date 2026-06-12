from __future__ import annotations

import asyncio
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
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


STALE_PROCESSING_MINUTES = int(os.getenv("ACTIVITY_EXTRACTION_STALE_MINUTES", "30"))
WORKER_ENABLED = os.getenv("ACTIVITY_EXTRACTION_WORKER_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
}
WORKER_CONCURRENCY = max(1, int(os.getenv("ACTIVITY_EXTRACTION_CONCURRENCY", "1")))
WORKER_POLL_INTERVAL_SECONDS = max(
    1.0,
    float(os.getenv("ACTIVITY_EXTRACTION_POLL_INTERVAL_SECONDS", "3")),
)

_worker_tasks: list[asyncio.Task[None]] = []
_worker_stop_event: asyncio.Event | None = None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_stale_processing_run(run: dict[str, Any]) -> bool:
    started_at = _parse_datetime(run.get("started_at") or run.get("created_at"))
    if not started_at:
        return False
    return datetime.now(timezone.utc) - started_at > timedelta(
        minutes=STALE_PROCESSING_MINUTES
    )


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
    if not activity.title.strip() or not activity.event_time_text.strip() and not start_at:
        review_status = "needs_review"

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


async def _execute_activity_extraction(
    article_id: str,
    run_id: str,
    *,
    input_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if input_snapshot is None:
        input_snapshot = await build_activity_extraction_input(article_id)
        await activity_run_repo.update_run(
            run_id,
            {
                "input_snapshot": input_snapshot,
            },
        )

    article = input_snapshot["article"]
    text = (
        input_snapshot.get("content", {}).get("markdown")
        or input_snapshot.get("content", {}).get("text")
        or ""
    )
    if not str(text).strip():
        message = "文章正文为空，无法抽取活动"
        await activity_run_repo.update_run(
            run_id,
            {
                "status": "fallback_required",
                "error": message,
                "finished_at": _now(),
                "locked_at": None,
                "locked_by": None,
            },
        )
        await article_repo.update_article(
            article_id,
            {
                "activity_extraction_status": "fallback_required",
                "activity_extraction_error": message,
            },
        )
        raise ValueError(message)

    try:
        output, raw_output_text, model = await asyncio.to_thread(
            extract_activities_with_llm,
            input_snapshot,
        )
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
                    "locked_at": None,
                    "locked_by": None,
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
                "locked_at": None,
                "locked_by": None,
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
                "locked_at": None,
                "locked_by": None,
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


async def _run_claimed_activity_extraction(run: dict[str, Any]) -> None:
    run_id = str(run.get("id") or "")
    article_id = str(run.get("article_id") or "")
    if not run_id or not article_id:
        logger.error(f"[activities.worker] invalid run payload={run}")
        return

    try:
        await _execute_activity_extraction(article_id, run_id)
    except Exception as exc:
        logger.exception(
            f"[activities.worker] failed article_id={article_id} run_id={run_id}"
        )


async def _activity_extraction_worker_loop(worker_id: str, stop_event: asyncio.Event) -> None:
    logger.info(f"[activities.worker] started worker_id={worker_id}")
    while not stop_event.is_set():
        try:
            stale_before = (
                datetime.now(timezone.utc) - timedelta(minutes=STALE_PROCESSING_MINUTES)
            ).isoformat()
            run = await activity_run_repo.claim_next_queued_run(
                worker_id=worker_id,
                stale_before=stale_before,
            )
            if not run:
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=WORKER_POLL_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    pass
                continue

            await article_repo.update_article(
                str(run.get("article_id") or ""),
                {
                    "activity_extraction_status": "processing",
                    "activity_extraction_error": "",
                },
            )
            await _run_claimed_activity_extraction(run)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(f"[activities.worker] loop error worker_id={worker_id}: {exc}")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=WORKER_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
    logger.info(f"[activities.worker] stopped worker_id={worker_id}")


async def start_activity_extraction_workers() -> None:
    global _worker_stop_event
    if not WORKER_ENABLED:
        logger.info("[activities.worker] disabled by ACTIVITY_EXTRACTION_WORKER_ENABLED")
        return
    if _worker_tasks:
        return

    _worker_stop_event = asyncio.Event()
    base_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    for index in range(WORKER_CONCURRENCY):
        worker_id = f"{base_id}-{index + 1}"
        _worker_tasks.append(
            asyncio.create_task(
                _activity_extraction_worker_loop(worker_id, _worker_stop_event),
                name=f"activity-extraction-worker-{index + 1}",
            )
        )
    logger.info(
        f"[activities.worker] started workers count={len(_worker_tasks)} "
        f"poll_interval={WORKER_POLL_INTERVAL_SECONDS}s"
    )


async def stop_activity_extraction_workers() -> None:
    global _worker_stop_event
    if _worker_stop_event:
        _worker_stop_event.set()
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
        _worker_tasks.clear()
    _worker_stop_event = None


async def start_activity_extraction(article_id: str) -> dict[str, Any]:
    article_rows = await article_repo.get_articles_by_id(article_id)
    if not article_rows:
        raise ValueError("文章不存在")

    active_run = await activity_run_repo.get_latest_active_run_by_article(article_id)
    if active_run:
        if active_run.get("status") == "processing" and _is_stale_processing_run(active_run):
            run_id = str(active_run.get("id") or "")
            await activity_run_repo.update_run(
                run_id,
                {
                    "status": "failed",
                    "error": "活动抽取任务超时未完成，已标记为失败",
                    "finished_at": _now(),
                    "locked_at": None,
                    "locked_by": None,
                },
            )
            await article_repo.update_article(
                article_id,
                {
                    "activity_extraction_status": "failed",
                    "activity_extraction_error": "活动抽取任务超时未完成，已标记为失败",
                },
            )
        else:
            return {
                "run_id": active_run.get("id"),
                "article_id": article_id,
                "status": active_run.get("status") or "queued",
                "already_running": True,
            }

    try:
        run = await activity_run_repo.create_run(
            {
                "article_id": article_id,
                "status": "queued",
                "model": "",
                "prompt_version": PROMPT_VERSION,
                "input_snapshot": {},
                "queued_at": _now(),
            }
        )
    except Exception as exc:
        active_run = await activity_run_repo.get_latest_active_run_by_article(article_id)
        if active_run:
            return {
                "run_id": active_run.get("id"),
                "article_id": article_id,
                "status": active_run.get("status") or "queued",
                "already_running": True,
            }
        raise exc

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

    return {
        "run_id": run_id,
        "article_id": article_id,
        "status": "queued",
        "already_running": False,
    }
