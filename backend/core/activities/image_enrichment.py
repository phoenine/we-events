from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Protocol

from core.activities import activity_repo
from core.activities.image_enrichment_agent import (
    OpenAICompatibleImageEnrichmentClient,
)
from core.activities.ocr_client import OpenAICompatibleOcrClient
from core.articles import article_repo


class ActivityImageEnrichmentError(RuntimeError):
    """Raised when an activity cannot be enriched from its article images."""


class ActivityImageOcrUpstreamError(RuntimeError):
    """Raised when every OCR provider request fails operationally."""


class SuggestionClient(Protocol):
    async def suggest(
        self,
        *,
        activity: dict[str, Any],
        article: dict[str, Any],
        images: list[dict[str, Any]],
        missing_fields: list[str],
    ) -> dict[str, Any]: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def missing_activity_fields(activity: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not activity.get("event_time_text") and not activity.get("start_at"):
        missing.append("event_time")
    if not str(activity.get("location_text") or "").strip():
        missing.append("location")

    method = str(activity.get("registration_method") or "unknown").strip()
    registration_text = str(activity.get("registration_text") or "").strip()
    registration_url = str(activity.get("registration_url") or "").strip()
    has_registration_hint = method not in {"", "none", "unknown"} or bool(
        registration_text or registration_url
    )
    if has_registration_hint and (
        method in {"", "unknown"} or not (registration_text or registration_url)
    ):
        missing.append("registration")
    return missing


async def get_image_enrichment_context(
    activity_id: str,
    *,
    activities_repo: Any = activity_repo,
    articles_repo: Any = article_repo,
) -> dict[str, Any]:
    activity = await activities_repo.get_activity_by_id(activity_id)
    if not activity:
        raise ActivityImageEnrichmentError("活动不存在")
    article_id = str(activity.get("article_id") or "")
    images = await articles_repo.get_article_images(article_id) if article_id else []
    return {
        "activity": activity,
        "missing_fields": missing_activity_fields(activity),
        "image_count": len(images),
        "images": images,
    }


async def _ocr_image(
    image: dict[str, Any],
    *,
    articles_repo: Any,
    ocr_client: OpenAICompatibleOcrClient,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    image_id = str(image.get("id") or "")
    cached_text = str(image.get("ocr_text") or "").strip()
    if image.get("ocr_status") == "completed":
        return (
            {
                "id": image_id,
                "position": image.get("position"),
                "text": cached_text,
                "provider": image.get("ocr_provider") or "cached",
            },
            None,
            False,
        )

    image_url = str(image.get("public_url") or image.get("origin_url") or "").strip()
    if not image_url:
        message = f"图片 {image_id or 'unknown'} 缺少可访问 URL"
        if image_id:
            await articles_repo.update_article_image(
                image_id,
                {
                    "ocr_status": "failed",
                    "ocr_error": message,
                    "ocr_finished_at": _now(),
                },
            )
        return None, message, False

    try:
        result = await ocr_client.recognize(image_url)
        if image_id:
            await articles_repo.update_article_image(
                image_id,
                {
                    "ocr_status": "completed",
                    "ocr_text": result.text,
                    "ocr_confidence": result.confidence,
                    "ocr_provider": result.provider,
                    "ocr_error": "",
                    "ocr_finished_at": _now(),
                },
            )
        return (
            {
                "id": image_id,
                "position": image.get("position"),
                "text": result.text,
                "provider": result.provider,
            },
            None,
            False,
        )
    except Exception as exc:
        message = f"图片 {image_id or 'unknown'} OCR 失败: {exc}"
        if image_id:
            await articles_repo.update_article_image(
                image_id,
                {
                    "ocr_status": "failed",
                    "ocr_error": str(exc),
                    "ocr_finished_at": _now(),
                },
            )
        return None, message, True


async def build_image_enrichment_preview(
    activity_id: str,
    *,
    activities_repo: Any = activity_repo,
    articles_repo: Any = article_repo,
    ocr_client: OpenAICompatibleOcrClient | None = None,
    suggestion_client: SuggestionClient | None = None,
) -> dict[str, Any]:
    activity = await activities_repo.get_activity_by_id(activity_id)
    if not activity:
        raise ActivityImageEnrichmentError("活动不存在")

    article_id = str(activity.get("article_id") or "")
    article_rows = await articles_repo.get_articles_by_id(article_id) if article_id else []
    if not article_rows:
        raise ActivityImageEnrichmentError("活动来源文章不存在")
    article = article_rows[0]
    images = await articles_repo.get_article_images(article_id)
    if not images:
        raise ActivityImageEnrichmentError("活动来源文章没有已采集图片")
    if ocr_client is None:
        ocr_client = OpenAICompatibleOcrClient.from_environment()
    if suggestion_client is None:
        suggestion_client = OpenAICompatibleImageEnrichmentClient.from_environment()

    semaphore = asyncio.Semaphore(3)

    async def run_ocr(image: dict[str, Any]):
        async with semaphore:
            return await _ocr_image(
                image,
                articles_repo=articles_repo,
                ocr_client=ocr_client,
            )

    results = await asyncio.gather(*(run_ocr(image) for image in images))
    ocr_images = [
        item for item, _error, _upstream_failed in results if item and item.get("text")
    ]
    ocr_warnings = [
        error for _item, error, _upstream_failed in results if error
    ]
    if not ocr_images:
        if results and all(upstream_failed for _item, _error, upstream_failed in results):
            raise ActivityImageOcrUpstreamError("所有文章图片 OCR 请求均失败")
        raise ActivityImageEnrichmentError("文章图片未识别出可用文字")

    preview = await suggestion_client.suggest(
        activity=activity,
        article=article,
        images=ocr_images,
        missing_fields=missing_activity_fields(activity),
    )
    return {
        "activity_id": activity_id,
        "current": activity,
        "suggestions": preview.get("suggestions") or {},
        "evidence": preview.get("evidence") or [],
        "warnings": [*ocr_warnings, *(preview.get("warnings") or [])],
        "images": ocr_images,
    }
