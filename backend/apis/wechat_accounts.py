import base64
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, cast, Optional
import json
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    Body,
)
from core.integrations.supabase.auth import get_current_user
from core.wechat_accounts import wechat_account_repo
from core.articles.collection_service import (
    enqueue_account_collection,
    get_article_collection_run,
)
from core.integrations.wx import search_Biz
from core.common.log import logger
from schemas import success_response, error_response

router = APIRouter(prefix="/wechat-accounts", tags=["公众号管理"])


def _normalize_wechat_faker_id(value: str | None) -> str:
    return str(value or "").strip()


def _derive_wechat_account_id(faker_id: str) -> str:
    try:
        decoded = base64.b64decode(faker_id).decode("utf-8")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40002, message="无效的公众号ID"),
        )
    if not decoded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40002, message="无效的公众号ID"),
        )
    return f"MP_WXS_{decoded}"


def _wechat_account_to_api(account: Dict[str, Any]) -> Dict[str, Any]:
    """将 wechat_accounts 表真实字段映射为前端 API 字段。"""
    return {
        "id": account.get("id"),
        "name": account.get("name") or account.get("mp_name"),
        "mp_name": account.get("mp_name") or account.get("name"),
        "logo_url": account.get("logo_url")
        or account.get("mp_cover")
        or account.get("cover"),
        "mp_cover": account.get("mp_cover")
        or account.get("cover")
        or account.get("logo_url"),
        "description": account.get("description") or account.get("mp_intro"),
        "mp_intro": account.get("mp_intro") or account.get("description"),
        "status": account.get("status"),
        "created_at": account.get("created_at"),
        "faker_id": account.get("faker_id"),
        "last_fetch": account.get("last_fetch"),
        "last_publish": account.get("last_publish"),
        # 兼容旧前端字段，底层映射到现有 wechat_accounts 列
        "update_time": account.get("update_time") or account.get("last_fetch"),
        "sync_time": account.get("sync_time") or account.get("last_fetch"),
    }


@router.get("/search/{kw}", summary="搜索公众号")
async def search_mp(
    kw: str = "",
    limit: int = 10,
    offset: int = 0,
    _current_user: dict = Depends(get_current_user),
):
    try:
        result = search_Biz(kw, limit=limit, offset=offset)
        data = {
            "list": result.get("list") if result is not None else [],
            "page": {"limit": limit, "offset": offset},
            "total": result.get("total") if result is not None else 0,
        }
        return success_response(data)
    except Exception as e:
        logger.info(f"搜索公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message="搜索公众号失败,请重新扫码授权！",
            ),
        )


@router.get("", summary="获取公众号列表")
async def list_wechat_accounts(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    _current_user: dict = Depends(get_current_user),
):
    try:
        filters = {}
        if kw:
            filters["name"] = {"ilike": f"%{kw}%"}

        # 获取总数
        total = await wechat_account_repo.count_wechat_accounts(filters=filters)

        # 获取分页数据
        accounts_raw = await wechat_account_repo.get_wechat_accounts(
            filters=filters,
            limit=limit,
            offset=offset,
            order_by="last_fetch.desc,created_at.desc",
        )
        accounts: List[Dict[str, Any]] = cast(List[Dict[str, Any]], accounts_raw)

        return success_response(
            {
                "list": [_wechat_account_to_api(account) for account in accounts],
                "page": {"limit": limit, "offset": offset, "total": total},
                "total": total,
            }
        )
    except Exception as e:
        logger.info(f"获取公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="获取公众号列表失败"),
        )


@router.get("/update/{wechat_account_id}", summary="更新公众号文章")
async def sync_wechat_account_articles(
    wechat_account_id: str,
    start_page: int = 0,
    end_page: int = 1,
    _current_user: dict = Depends(get_current_user),
):
    try:
        result = await enqueue_account_collection(
            wechat_account_id,
            start_page=start_page,
            max_page=end_page,
        )
        return success_response(result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=40001, message=str(e)),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新公众号文章异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"更新公众号文章{str(e)}"),
        )


@router.get("/collection-runs/{run_id}", summary="获取文章采集任务状态")
async def get_article_collection_run_status(
    run_id: str,
    _current_user: dict = Depends(get_current_user),
):
    try:
        run = await get_article_collection_run(run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40404, message="文章采集任务不存在"),
            )
        return success_response(run)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文章采集任务状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"获取文章采集任务状态失败: {str(e)}"),
        )


@router.get("/{wechat_account_id}", summary="获取公众号详情")
async def get_wechat_account(
    wechat_account_id: str,
):
    try:
        # 兼容两种入参：
        # 1) 系统内主键 id（如 MP_WXS_xxx）
        # 2) 微信 fakeid（如 MzI3NDQ0MTI2OQ==）
        mp = await wechat_account_repo.get_wechat_account_by_id(wechat_account_id)
        if not mp:
            mp = await wechat_account_repo.get_wechat_account_by_faker_id(
                wechat_account_id
            )
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="公众号不存在"),
            )
        return success_response(_wechat_account_to_api(mp))
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="获取公众号详情失败"),
        )


@router.post("/by_article", summary="通过文章链接获取公众号详情")
async def get_wechat_account_by_article(
    url: str = Query(..., min_length=1), _current_user: dict = Depends(get_current_user)
):
    try:
        from driver.wx.service import fetch_article, get_state as wx_get_state

        user_id = (_current_user or {}).get("id")
        logger.info(f"[wx-by-article] start user_id={user_id} url={url}")

        # 在后台线程中执行同步的 Playwright 调用，避免在事件循环里直接使用 Sync API
        loop = asyncio.get_running_loop()
        env = await loop.run_in_executor(None, fetch_article, url)
        logger.info(
            f"[wx-by-article] fetch_article done ok={bool(env and env.get('ok'))} "
            f"state={(env or {}).get('state')}"
        )

        if not env or not env.get("ok"):
            # 统一错误 envelope：尽量透传 reason，保持原有错误响应风格
            err = (env or {}).get("error") or {}
            msg = err.get("message") or "获取公众号信息失败"
            reason = err.get("reason")
            logger.warning(
                f"[wx-by-article] failed user_id={user_id} "
                f"state={(env or {}).get('state')} code={err.get('code')} stage={err.get('stage')} "
                f"message={msg} reason={reason} retryable={err.get('retryable')} "
                f"raw={(err.get('raw') or '')[:800]}"
            )
            try:
                state_env = wx_get_state()
                logger.info(
                    f"[wx-by-article] current_wx_state user_id={user_id} state_env={state_env}"
                )
            except Exception as state_err:
                logger.warning(f"[wx-by-article] get_state failed: {state_err}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=error_response(
                    code=50001,
                    message=f"{msg}: {reason}" if reason else msg,
                    data=env,
                ),
            )

        article_data = env.get("data")
        try:
            if isinstance(article_data, dict):
                mp_info = article_data.get("mp_info")
                logger.info(
                    f"[wx-by-article] success user_id={user_id} "
                    f"data_keys={list(article_data.keys())} "
                    f"mp_info_keys={list(mp_info.keys()) if isinstance(mp_info, dict) else None}"
                )
                logger.info(
                    "[wx-by-article] success_payload_preview "
                    + json.dumps(
                        {
                            "mp_info": (
                                mp_info if isinstance(mp_info, dict) else mp_info
                            ),
                            "title": article_data.get("title"),
                            "url": article_data.get("url"),
                        },
                        ensure_ascii=False,
                        default=str,
                    )[:1200]
                )
            else:
                logger.info(
                    f"[wx-by-article] success user_id={user_id} non_dict_data_type={type(article_data)}"
                )
        except Exception as log_err:
            logger.warning(f"[wx-by-article] success logging failed: {log_err}")

        return success_response(article_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[wx-by-article] unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"获取公众号信息失败: {str(e)}"),
        )


@router.post("", summary="添加公众号")
async def create_wechat_account(
    mp_name: str = Body(..., min_length=1, max_length=255),
    mp_cover: str = Body(None, max_length=255),
    wechat_account_id: str = Body(None, max_length=255),
    avatar: str = Body(None, max_length=500),
    mp_intro: str = Body(None, max_length=255),
    _current_user: dict = Depends(get_current_user),
):
    try:
        faker_id = _normalize_wechat_faker_id(wechat_account_id)
        if not faker_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40001, message="缺少公众号ID"),
            )

        account_id = _derive_wechat_account_id(faker_id)

        cover_path: Optional[str] = avatar or mp_cover

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # 公众号去重只使用稳定标识：系统 id / 微信 fakeid，不使用公众号名称。
        existing_account_raw = await wechat_account_repo.get_wechat_account_by_identity(
            account_id=account_id,
            faker_id=faker_id,
        )
        existing_account: Dict[str, Any] = cast(Dict[str, Any], existing_account_raw)

        if existing_account:
            # 更新现有记录
            update_data: Dict[str, Any] = {
                "name": mp_name,
                "description": mp_intro,
                "updated_at": now_iso,
            }
            if cover_path:
                update_data["logo_url"] = cover_path

            await wechat_account_repo.update_wechat_account(
                existing_account["id"], update_data
            )
            account = {**existing_account, **update_data}
        else:
            # 创建新的公众号账号记录
            account_data: Dict[str, Any] = {
                "id": account_id,
                "name": mp_name,
                "logo_url": cover_path,
                "description": mp_intro,
                "status": 1,  # 默认启用状态
                "created_at": now_iso,
                "updated_at": now_iso,
                "faker_id": faker_id,
            }
            account = await wechat_account_repo.create_wechat_account(account_data)

        # 订阅添加只保存公众号信息，不自动触发采集。
        # 文章抓取改为由用户手动点击“刷新”触发，以降低微信风控概率。

        return success_response(
            _wechat_account_to_api(
                {**account, "faker_id": account.get("faker_id", faker_id)}
            )
        )
    except HTTPException:
        # 直接透传上面主动抛出的 HTTPException
        raise
    except Exception as e:
        logger.info(f"添加公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="添加公众号失败"),
        )


@router.delete("/{wechat_account_id}", summary="删除订阅号")
async def delete_mp(
    wechat_account_id: str,
    _current_user: dict = Depends(get_current_user),
):
    try:
        mp = await wechat_account_repo.get_wechat_account_by_id(wechat_account_id)
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="订阅号不存在"),
            )

        await wechat_account_repo.delete_wechat_account(wechat_account_id)
        return success_response({"message": "订阅号删除成功", "id": wechat_account_id})
    except Exception as e:
        logger.info(f"删除订阅号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="删除订阅号失败"),
        )
