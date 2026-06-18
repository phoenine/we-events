import asyncio

from fastapi import APIRouter, Depends, HTTPException, status as fast_status, Query, Body
from core.integrations.supabase.auth import get_current_user
from core.articles import article_repo
from core.wechat_accounts import wechat_account_repo
from core.articles.storage_cleanup import delete_article_storage_objects
from core.articles.quality_service import reclassify_article_content_statuses
from core.common.log import logger
from schemas import success_response, error_response, format_search_kw
from typing import Optional, List, Dict, Any, cast
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/articles", tags=["文章管理"])
_reclassify_content_status_lock = asyncio.Lock()


async def _safe_delete_article_image_mapping(article_id: str) -> None:
    if not article_id:
        return
    try:
        await article_repo.delete_article_images_by_article(article_id)
    except Exception as e:
        logger.warning(f"删除文章图片映射失败 article_id={article_id}: {e}")


async def _safe_delete_article_image_mappings(article_ids: List[str]) -> None:
    ids = [str(i).strip() for i in (article_ids or []) if str(i).strip()]
    if not ids:
        return
    try:
        await article_repo.delete_article_images_by_articles(ids)
    except Exception as e:
        logger.warning(f"批量删除文章图片映射失败 count={len(ids)}: {e}")


@router.get("", summary="获取文章列表")
async def get_articles(
    wechat_account_id: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=100),
    _current_user: dict = Depends(get_current_user),
):
    try:
        articles_raw = await article_repo.get_articles(
            wechat_account_id=wechat_account_id,
            limit=limit,
            offset=offset,
            order_by="publish_time.desc",
        )
        # 显式标注类型，便于静态类型检查
        articles: List[Dict[str, Any]] = cast(List[Dict[str, Any]], articles_raw)

        total = await article_repo.count_articles(
            wechat_account_id=wechat_account_id,
        )

        # 获取相关公众号账号信息
        wechat_account_ids = {article.get("wechat_account_id") for article in articles}
        mp_names = {}

        if wechat_account_ids:
            accounts_raw = await wechat_account_repo.get_wechat_accounts()
            accounts: List[Dict[str, Any]] = cast(List[Dict[str, Any]], accounts_raw)
            for account in accounts:
                if account["id"] in wechat_account_ids:
                    mp_names[account["id"]] = account["name"]

        # 合并公众号名称到文章列表
        article_list = []
        for article in articles:
            article_dict = article.copy()
            article_dict["mp_name"] = mp_names.get(article.get("wechat_account_id"), "未知公众号")
            article_list.append(article_dict)

        return success_response({"list": article_list, "total": total})

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"获取文章列表失败: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(code=50001, message=f"获取文章列表失败: {str(e)}"),
        )


@router.get("/{article_id}", summary="获取文章详情")
async def get_article_detail(
    article_id: str,
    _current_user: dict = Depends(get_current_user),
):
    try:
        article_rows_raw = await article_repo.get_articles_by_id(article_id)
        article_rows: List[Dict[str, Any]] = cast(List[Dict[str, Any]], article_rows_raw)
        if not article_rows:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="文章不存在"),
            )
        return success_response(article_rows[0])

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"获取文章详情失败: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(code=50001, message=f"获取文章详情失败: {str(e)}"),
        )


@router.get("/{article_id}/next", summary="获取下一篇文章")
async def get_next_article(
    article_id: str, _current_user: dict = Depends(get_current_user)
):
    try:
        # 获取当前文章
        current_article_rows_raw = await article_repo.get_articles_by_id(article_id)
        current_article_rows: List[Dict[str, Any]] = cast(
            List[Dict[str, Any]], current_article_rows_raw
        )
        if not current_article_rows:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="当前文章不存在"),
            )
        current_article = current_article_rows[0]
        # 获取同一公众号的文章
        articles_raw = await article_repo.get_articles(
            wechat_account_id=current_article["wechat_account_id"], order_by="publish_time.desc"
        )
        articles: List[Dict[str, Any]] = cast(List[Dict[str, Any]], articles_raw)

        # 找到当前文章的位置
        current_index = None
        for i, article in enumerate(articles):
            if article["id"] == article_id:
                current_index = i
                break

        if current_index is None or current_index == 0:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(code=40402, message="没有下一篇文章"),
            )

        # 返回下一篇文章
        next_article = articles[current_index - 1]
        return success_response(next_article)

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"获取下一篇文章失败: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(code=50001, message=f"获取下一篇文章失败: {str(e)}"),
        )


@router.get("/{article_id}/prev", summary="获取上一篇文章")
async def get_prev_article(
    article_id: str, _current_user: dict = Depends(get_current_user)
):
    try:
        # 获取当前文章
        current_article_rows_raw = await article_repo.get_articles_by_id(article_id)
        current_article_rows: List[Dict[str, Any]] = cast(
            List[Dict[str, Any]], current_article_rows_raw
        )
        if not current_article_rows:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="当前文章不存在"),
            )
        current_article = current_article_rows[0]

        # 获取同一公众号的文章
        articles_raw = await article_repo.get_articles(
            wechat_account_id=current_article["wechat_account_id"], order_by="publish_time.desc"
        )
        articles: List[Dict[str, Any]] = cast(List[Dict[str, Any]], articles_raw)

        # 找到当前文章的位置
        current_index = None
        for i, article in enumerate(articles):
            if article["id"] == article_id:
                current_index = i
                break

        if current_index is None or current_index >= len(articles) - 1:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(code=40403, message="没有上一篇文章"),
            )

        # 返回上一篇文章
        prev_article = articles[current_index + 1]
        return success_response(prev_article)

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"获取上一篇文章失败: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(code=50001, message=f"获取上一篇文章失败: {str(e)}"),
        )


@router.delete("/clean_expired", summary="清理过期文章(删除15天前的publish_time)")
async def clean_expired_articles(_current_user: dict = Depends(get_current_user)):
    try:
        cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=15)).timestamp())
        expired_rows_raw = await article_repo.get_articles_base(
            filters={"publish_time": {"lt": cutoff_ts}}
        )
        expired_rows: List[Dict[str, Any]] = cast(List[Dict[str, Any]], expired_rows_raw)
        article_ids = [str(row.get("id")) for row in expired_rows if row.get("id")]

        storage_deleted_count = 0
        for article in expired_rows:
            storage_deleted_count += await delete_article_storage_objects(article)

        deleted_count = await article_repo.clean_expired_articles(days=15)
        await _safe_delete_article_image_mappings(article_ids)
        return success_response(
            {
                "message": "清理过期文章成功",
                "deleted_count": deleted_count,
                "storage_deleted_count": storage_deleted_count,
            }
        )
    except Exception as e:
        logger.error(f"清理过期文章错误: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_201_CREATED,
            detail=error_response(code=50001, message="清理过期文章失败"),
        )


@router.delete("/clean", summary="清理孤儿文章(MP_ID不存在于wechat_accounts表中的文章)")
async def clean_orphan_articles(_current_user: dict = Depends(get_current_user)):
    try:
        # 获取所有有效的公众号账号 ID；这里的“孤儿文章”不是空正文/不可访问文章。
        accounts_raw = await wechat_account_repo.get_wechat_accounts()
        accounts: List[Dict[str, Any]] = cast(List[Dict[str, Any]], accounts_raw)
        valid_account_ids = {account["id"] for account in accounts}

        # 获取所有文章
        articles_raw = await article_repo.get_articles()
        articles: List[Dict[str, Any]] = cast(List[Dict[str, Any]], articles_raw)

        deleted_count = 0
        storage_deleted_count = 0
        for article in articles:
            if article["wechat_account_id"] not in valid_account_ids:
                storage_deleted_count += await delete_article_storage_objects(article)
                await article_repo.delete_article(article["id"])
                await _safe_delete_article_image_mapping(str(article["id"]))
                deleted_count += 1

        return success_response(
            {
                "message": "清理孤儿文章成功",
                "deleted_count": deleted_count,
                "storage_deleted_count": storage_deleted_count,
            }
        )
    except Exception as e:
        logger.error(f"清理孤儿文章错误: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_201_CREATED,
            detail=error_response(code=50001, message="清理孤儿文章失败"),
        )


@router.delete("/clean_duplicate_articles", summary="清理重复文章")
async def clean_duplicate(_current_user: dict = Depends(get_current_user)):
    try:
        from core.articles.cleaning import clean_duplicate_articles

        (msg, deleted_count) = clean_duplicate_articles()
        return success_response({"message": msg, "deleted_count": deleted_count})
    except Exception as e:
        logger.error(f"清理重复文章: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_201_CREATED,
            detail=error_response(code=50001, message="清理重复文章"),
        )


@router.post("/reclassify_content_status", summary="重分类文章正文抓取状态")
async def reclassify_content_status(
    limit: Optional[int] = Query(None, ge=1, le=5000),
    dry_run: bool = Query(False),
    _current_user: dict = Depends(get_current_user),
):
    if _reclassify_content_status_lock.locked():
        raise HTTPException(
            status_code=fast_status.HTTP_409_CONFLICT,
            detail=error_response(code=40901, message="重分类任务正在运行"),
        )
    try:
        async with _reclassify_content_status_lock:
            summary = await reclassify_article_content_statuses(
                article_repo,
                limit=limit,
                dry_run=dry_run,
            )
        return success_response(summary)
    except Exception as e:
        logger.error(f"重分类文章正文抓取状态失败: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(code=50001, message="重分类文章正文抓取状态失败"),
        )


@router.delete("/batch", summary="批量删除文章")
async def delete_articles_batch(
    article_ids: List[str] = Body(..., embed=True),
    _current_user: dict = Depends(get_current_user),
):
    try:
        ids = [str(i).strip() for i in (article_ids or []) if str(i).strip()]
        if not ids:
            raise HTTPException(
                status_code=fast_status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40001, message="article_ids 不能为空"),
            )

        rows_raw = await article_repo.get_articles_base(filters={"id": {"in": ids}})
        rows: List[Dict[str, Any]] = cast(List[Dict[str, Any]], rows_raw)
        rows_by_id = {str(r.get("id")): r for r in rows}

        deleted_count = 0
        storage_deleted_count = 0
        missing_ids: List[str] = []
        failed_ids: List[str] = []

        for article_id in ids:
            article = rows_by_id.get(article_id)
            if not article:
                missing_ids.append(article_id)
                continue
            try:
                storage_deleted_count += await delete_article_storage_objects(article)
                await article_repo.delete_article(article_id)
                await _safe_delete_article_image_mapping(article_id)
                deleted_count += 1
            except Exception:
                failed_ids.append(article_id)

        return success_response(
            {
                "deleted_count": deleted_count,
                "storage_deleted_count": storage_deleted_count,
                "missing_ids": missing_ids,
                "failed_ids": failed_ids,
            },
            message=f"批量删除完成，成功 {deleted_count} 篇",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除文章失败: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(code=50001, message=f"批量删除文章失败: {str(e)}"),
        )


@router.delete("/{article_id}", summary="删除文章")
async def delete_article(
    article_id: str, _current_user: dict = Depends(get_current_user)
):
    try:
        # 检查文章是否存在
        article_rows = await article_repo.get_articles_by_id(article_id)
        if not article_rows:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(code=40401, message="文章不存在"),
            )
        article = article_rows[0]

        # 删除关联的 storage 图片对象（best-effort）
        storage_deleted = await delete_article_storage_objects(article)

        # 删除文章
        await article_repo.delete_article(article_id)
        await _safe_delete_article_image_mapping(article_id)

        return success_response(
            {"storage_deleted": storage_deleted},
            message="文章已删除",
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"删除文章失败: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(code=50001, message=f"删除文章失败: {str(e)}"),
        )
