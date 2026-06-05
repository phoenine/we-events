from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Body,
    status as fast_status,
)
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from core.integrations.supabase.auth import get_current_user
from core.articles import article_repo
from core.activities import activity_repo
from core.activities.agent import analyze_article_for_activity
from core.activities.service import upsert_activity_from_article
from core.common.log import logger
from schemas import success_response, error_response, ActivityCreate, ActivityUpdate

router = APIRouter(prefix="/activities", tags=["活动"])


def _get_date_range(scope: str):
    now = datetime.now(timezone.utc)
    start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    if scope in ("today", "day"):
        return start_of_day, start_of_day + timedelta(days=1)
    elif scope == "week":
        start_of_week = start_of_day - timedelta(days=now.weekday())
        end_of_week = start_of_week + timedelta(days=7)
        return start_of_week, end_of_week
    else:
        return None, None


@router.post("/fetch", summary="活动fetch（按日期筛选文章并分析生成activities）")
async def fetch_activities(
    scope: str = Query("today", pattern="^(today|day|week|all)$"),
    limit: int = Query(200, ge=1, le=200),
    payload: Optional[Dict[str, Any]] = Body(None),
    _current_user: dict = Depends(get_current_user),
):
    # 如果请求体提供了 scope/limit，则从 JSON body 中标准化（支持 {"scope":"week","limit":100}）
    if payload:
        body_scope = (payload.get("scope") or "").strip().lower()
        if body_scope in {"today", "day", "week", "all"}:
            scope = "today" if body_scope == "day" else body_scope
        body_limit = payload.get("limit")
        try:
            if isinstance(body_limit, int) and 1 <= body_limit <= 200:
                limit = body_limit
        except Exception:
            pass
    try:
        logger.info(f"[activities.fetch] scope={scope}, limit={limit}")
        start, end = _get_date_range(scope)
        if start and end:
            logger.info(
                f"[activities.fetch] date_range: {start.isoformat()} ~ {end.isoformat()}"
            )

        # 获取文章列表
        if start and end:
            articles = await article_repo.get_articles_by_time_range(
                start, end, limit=limit
            )
        else:
            articles = await article_repo.get_articles(limit=limit)

        logger.info(f"[activities.fetch] scanned_articles={len(articles)}")

        # 获取已存在的活动文章ID
        existing_ids = set(await activity_repo.get_activity_article_ids())
        logger.info(f"[activities.fetch] existing_activities={len(existing_ids)}")

        created, updated = [], []
        for art in articles:
            if art["id"] in existing_ids:
                logger.info(f"[activities.fetch] skip existing article_id={art['id']}")
                continue
            logger.debug(
                "[activities.fetch] article "
                f"id={art['id']}, title={ (art.get('title') or '')[:50]!r }, "
                f"publish_time={art.get('publish_time')}, "
                f"publish_at={art.get('publish_at')}, "
                f"url={art.get('url')}"
            )

            analysis = analyze_article_for_activity(
                art.get("title"), art.get("content"), art.get("url")
            )
            logger.debug(
                f"[activities.fetch] analysis article_id={art['id']} -> {analysis}"
            )

            if not analysis.get("is_event", False):
                logger.info(
                    f"[activities.fetch] skip non-activity article_id={art['id']}"
                )
                await article_repo.update_article(
                    art["id"], {"activity_extraction_status": "not_activity"}
                )
                continue

            activity, created_flag = await upsert_activity_from_article(art, analysis)
            await article_repo.update_article(
                art["id"], {"activity_extraction_status": "extracted"}
            )
            if created_flag:
                created.append(activity["article_id"])
            else:
                updated.append(activity["article_id"])

        logger.info(
            f"[activities.fetch] result created={len(created)}, updated={len(updated)}"
        )
        return success_response(
            data={
                "scope": scope,
                "scanned": len(articles),
                "created_count": len(created),
                "updated_count": len(updated),
                "created_article_ids": created,
                "updated_article_ids": updated,
            }
        )
    except Exception as e:
        logger.exception(f"[activities.fetch] failed: {e}")
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"活动fetch失败: {str(e)}"),
        )


@router.post("", summary="创建活动记录")
async def create_activity(
    payload: ActivityCreate = Body(...),
    _current_user: dict = Depends(get_current_user),
):
    try:
        now = datetime.now(timezone.utc)
        created_at = payload.created_at or now
        updated_at = payload.updated_at or now

        # 统一从文章库获取URL
        article_rows = await article_repo.get_articles_by_id(payload.article_id)
        if not article_rows:
            raise HTTPException(
                status_code=fast_status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40011, message="关联文章不存在"),
            )
        art = article_rows[0]

        activity_data = {
            "article_id": payload.article_id,
            "source_wechat_account_id": payload.source_wechat_account_id
            or art.get("wechat_account_id"),
            "title": payload.title or art.get("title") or "",
            "original_title": payload.original_title or art.get("title") or "",
            "registration_time_text": payload.registration_time_text or "",
            "registration_method": payload.registration_method
            or (art.get("url") or ""),
            "event_time_text": payload.event_time_text or "",
            "event_fee": payload.event_fee or "无",
            "audience": payload.audience or "无",
            "article_url": art.get("url") or "无",
            "status": payload.status or "active",
            "extraction_status": payload.extraction_status or "reviewed",
            "fallback_reason": payload.fallback_reason,
            "confidence": payload.confidence,
            "extracted_by": payload.extracted_by or "manual",
            "extraction_model": payload.extraction_model,
            "extraction_raw": payload.extraction_raw or {},
            "reviewed_at": (
                payload.reviewed_at.isoformat()
                if payload.reviewed_at
                else now.isoformat()
            ),
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
        }

        activity = await activity_repo.create_activity(activity_data)
        return success_response(activity)
    except Exception as e:
        logger.exception(f"[activities.create] failed: {e}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40001, message=f"创建失败: {str(e)}"),
        )


@router.get("", summary="查询活动记录列表")
async def list_activities(
    article_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _current_user: dict = Depends(get_current_user),
):
    try:
        activities = await activity_repo.get_activities(
            article_id=article_id, limit=limit, offset=offset
        )
        return success_response(activities)
    except Exception as e:
        logger.exception(f"[activities.list] failed: {e}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40002, message=f"查询失败: {str(e)}"),
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
        return success_response(activity)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"[activities.get] failed: {e}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40003, message=f"获取失败: {str(e)}"),
        )


@router.put("/{activity_id}", summary="更新活动记录")
async def update_activity(
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

        now = datetime.now(timezone.utc)
        update_data = {}

        if payload.title is not None:
            update_data["title"] = payload.title
        if payload.original_title is not None:
            update_data["original_title"] = payload.original_title
        if payload.registration_time_text is not None:
            update_data["registration_time_text"] = payload.registration_time_text
        if payload.registration_method is not None:
            update_data["registration_method"] = payload.registration_method
        if payload.event_time_text is not None:
            update_data["event_time_text"] = payload.event_time_text
        if payload.event_fee is not None:
            update_data["event_fee"] = payload.event_fee
        if payload.audience is not None:
            update_data["audience"] = payload.audience
        if payload.status is not None:
            update_data["status"] = payload.status
        if payload.source_wechat_account_id is not None:
            update_data["source_wechat_account_id"] = payload.source_wechat_account_id
        if payload.extraction_status is not None:
            update_data["extraction_status"] = payload.extraction_status
        if payload.fallback_reason is not None:
            update_data["fallback_reason"] = payload.fallback_reason
        if payload.confidence is not None:
            update_data["confidence"] = payload.confidence
        if payload.extracted_by is not None:
            update_data["extracted_by"] = payload.extracted_by
        if payload.extraction_model is not None:
            update_data["extraction_model"] = payload.extraction_model
        if payload.extraction_raw is not None:
            update_data["extraction_raw"] = payload.extraction_raw
        if payload.reviewed_at is not None:
            update_data["reviewed_at"] = payload.reviewed_at.isoformat()

        # 每次更新都从文章库刷新一次URL（保证一致性）
        article_rows = await article_repo.get_articles_by_id(activity["article_id"])
        art = article_rows[0] if article_rows else None
        update_data["article_url"] = (
            payload.article_url
            if payload.article_url is not None
            else (art.get("url") if art else None) or "无"
        )
        update_data.setdefault("extraction_status", "reviewed")

        # 时间字段更新（允许覆盖created_at；若未提供updated_at则写当前时间）
        if payload.created_at is not None:
            update_data["created_at"] = payload.created_at.isoformat()
        update_data["updated_at"] = (
            payload.updated_at.isoformat() if payload.updated_at else now.isoformat()
        )

        updated_activity = await activity_repo.update_activity(activity_id, update_data)
        return success_response(updated_activity[0] if updated_activity else activity)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"[activities.update] failed: {e}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40004, message=f"更新失败: {str(e)}"),
        )


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
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"[activities.delete] failed: {e}")
        raise HTTPException(
            status_code=fast_status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40005, message=f"删除失败: {str(e)}"),
        )
