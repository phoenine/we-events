from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status as fast_status

from core.activities import activity_repo, activity_run_repo
from core.activities.extraction_output import compute_event_status
from core.activities.image_enrichment import (
    ActivityImageEnrichmentError,
    ActivityImageOcrUpstreamError,
    build_image_enrichment_preview,
    get_image_enrichment_context,
)
from core.activities.image_enrichment_agent import ImageEnrichmentConfigurationError
from core.activities.ocr_client import OcrConfigurationError
from core.activities.service import start_activity_extraction
from core.articles import article_repo
from core.common.log import logger
from core.common.runtime_settings import runtime_settings
from core.integrations.supabase.auth import get_current_admin_user, get_current_user
from schemas import ActivityCreate, ActivityUpdate, error_response, success_response


router = APIRouter(prefix="/activities", tags=["活动"])


def _drop_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


@router.post("/extract/article/{article_id}", summary="从单篇文章抽取活动")
async def extract_article_activities(
    article_id: str,
    _current_user: dict = Depends(get_current_user),
):
    try:
        result = await start_activity_extraction(article_id)
        return success_response(result)
    except ValueError as exc:
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40006, message=str(exc)),
        )
    except Exception as exc:
        logger.exception(f"[activities.extract.api] failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50006, message=f"活动抽取失败: {str(exc)}"),
        )


@router.get("/extraction-runs/{run_id}", summary="获取活动抽取运行记录")
async def get_activity_extraction_run(
    run_id: str,
    _current_user: dict = Depends(get_current_user),
):
    try:
        run = await activity_run_repo.get_run_by_id(run_id)
        if not run:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40402, message="活动抽取记录不存在"),
            )
        return success_response(run)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"[activities.run.get] failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40007, message=f"获取失败: {str(exc)}"),
        )


@router.get(
    "/{activity_id}/image-enrichment-context",
    summary="获取活动图片补充上下文",
)
async def activity_image_enrichment_context(
    activity_id: str,
    _current_user: dict = Depends(get_current_user),
):
    try:
        context = await get_image_enrichment_context(activity_id)
        context["ocr_enabled"] = await runtime_settings.get_bool("ocr.enabled", False)
        return success_response(context)
    except ActivityImageEnrichmentError as exc:
        status_code = (
            fast_status.HTTP_404_NOT_FOUND
            if "不存在" in str(exc)
            else fast_status.HTTP_409_CONFLICT
        )
        raise HTTPException(
            status_code=status_code,
            detail=error_response(code=status_code, message=str(exc)),
        )
    except Exception as exc:
        logger.exception(f"[activities.image-enrichment.context] failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50012, message="获取图片补充上下文失败"),
        )


@router.post(
    "/{activity_id}/image-enrichment-preview",
    summary="生成活动图片补充预览",
)
async def preview_activity_image_enrichment(
    activity_id: str,
    _current_user: dict = Depends(get_current_admin_user),
):
    if not await runtime_settings.get_bool("ocr.enabled", False):
        raise HTTPException(
            status_code=fast_status.HTTP_409_CONFLICT,
            detail=error_response(code=40912, message="图片 OCR 补充功能未启用"),
        )
    try:
        preview = await build_image_enrichment_preview(activity_id)
        return success_response(preview)
    except (OcrConfigurationError, ImageEnrichmentConfigurationError):
        raise HTTPException(
            status_code=fast_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_response(code=50312, message="OCR 或 LLM API 未配置"),
        )
    except ActivityImageOcrUpstreamError as exc:
        logger.warning(f"[activities.image-enrichment.ocr] upstream failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_502_BAD_GATEWAY,
            detail=error_response(code=50213, message="OCR 服务暂时不可用"),
        )
    except ActivityImageEnrichmentError as exc:
        status_code = (
            fast_status.HTTP_404_NOT_FOUND
            if "不存在" in str(exc)
            else fast_status.HTTP_409_CONFLICT
        )
        raise HTTPException(
            status_code=status_code,
            detail=error_response(code=status_code, message=str(exc)),
        )
    except Exception as exc:
        logger.exception(f"[activities.image-enrichment.preview] failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_502_BAD_GATEWAY,
            detail=error_response(code=50212, message="生成图片补充建议失败"),
        )


@router.post("", summary="创建活动记录")
async def create_activity(
    payload: ActivityCreate = Body(...),
    _current_user: dict = Depends(get_current_user),
):
    try:
        article_rows = await article_repo.get_articles_by_id(payload.article_id)
        if not article_rows:
            raise HTTPException(
                status_code=fast_status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40011, message="关联文章不存在"),
            )
        article = article_rows[0]

        data = payload.model_dump(mode="json")
        data["source_wechat_account_id"] = (
            payload.source_wechat_account_id or article.get("wechat_account_id")
        )
        data["article_url"] = payload.article_url or article.get("url") or ""
        data["event_status"] = compute_event_status(payload.start_at, payload.end_at)
        activity = await activity_repo.create_activity(_drop_none(data))
        return success_response(activity)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"[activities.create] failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40001, message=f"创建失败: {str(exc)}"),
        )


@router.get("", summary="查询活动记录列表")
async def list_activities(
    article_id: str | None = Query(None),
    review_status: str | None = Query(None),
    event_status: str | None = Query(None),
    source_wechat_account_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _current_user: dict = Depends(get_current_user),
):
    try:
        requested_status = event_status if isinstance(event_status, str) else None
        page_limit = limit if isinstance(limit, int) else 100
        page_offset = offset if isinstance(offset, int) else 0

        async def fetch_batch(batch_limit: int, batch_offset: int):
            rows = await activity_repo.get_activities(
                article_id=article_id,
                review_status=review_status,
                event_status=None,
                source_wechat_account_id=source_wechat_account_id,
                date_from=date_from,
                date_to=date_to,
                limit=batch_limit,
                offset=batch_offset,
            )
            for row in rows:
                row["event_status"] = compute_event_status(
                    row.get("start_at"),
                    row.get("end_at"),
                )
            return rows

        if requested_status:
            matches = []
            scan_offset = 0
            scan_limit = 500
            required_matches = page_offset + page_limit
            while len(matches) < required_matches:
                batch = await fetch_batch(scan_limit, scan_offset)
                matches.extend(
                    row for row in batch if row["event_status"] == requested_status
                )
                if len(batch) < scan_limit:
                    break
                scan_offset += len(batch)
            activities = matches[page_offset:required_matches]
        else:
            activities = await fetch_batch(page_limit, page_offset)

        return success_response(activities)
    except Exception as exc:
        logger.exception(f"[activities.list] failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40002, message=f"查询失败: {str(exc)}"),
        )


@router.get("/{activity_id}", summary="获取活动记录详情")
async def get_activity(
    activity_id: str,
    _current_user: dict = Depends(get_current_user),
):
    try:
        activity = await activity_repo.get_activity_by_id(activity_id)
        if not activity:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="活动记录不存在"),
            )
        activity["event_status"] = compute_event_status(
            activity.get("start_at"),
            activity.get("end_at"),
        )
        return success_response(activity)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"[activities.get] failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40003, message=f"获取失败: {str(exc)}"),
        )


@router.patch("/{activity_id}", summary="更新活动记录")
async def patch_activity(
    activity_id: str,
    payload: ActivityUpdate = Body(...),
    _current_user: dict = Depends(get_current_user),
):
    try:
        activity = await activity_repo.get_activity_by_id(activity_id)
        if not activity:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="活动记录不存在"),
            )

        data = _drop_none(payload.model_dump(mode="json"))
        data.pop("event_status", None)
        data["event_status"] = compute_event_status(
            data.get("start_at", activity.get("start_at")),
            data.get("end_at", activity.get("end_at")),
        )
        updated = await activity_repo.update_activity(activity_id, data)
        return success_response(updated[0] if updated else activity)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"[activities.patch] failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40004, message=f"更新失败: {str(exc)}"),
        )


@router.put("/{activity_id}", summary="更新活动记录")
async def update_activity(
    activity_id: str,
    payload: ActivityUpdate = Body(...),
    _current_user: dict = Depends(get_current_user),
):
    return await patch_activity(activity_id, payload, _current_user)


@router.delete("/{activity_id}", summary="删除活动记录")
async def delete_activity(
    activity_id: str,
    _current_user: dict = Depends(get_current_user),
):
    try:
        activity = await activity_repo.get_activity_by_id(activity_id)
        if not activity:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="活动记录不存在"),
            )
        await activity_repo.delete_activity(activity_id)
        return success_response({"deleted_id": activity_id})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"[activities.delete] failed: {exc}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40005, message=f"删除失败: {str(exc)}"),
        )
