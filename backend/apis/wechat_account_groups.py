import json
import threading
import time
from fastapi import APIRouter, Body, Depends, HTTPException, status
from datetime import datetime, timezone
from core.wechat_account_groups import wechat_account_group_repo
from core.wechat_accounts import wechat_account_repo
from core.wechat_accounts.collector import collect_wechat_account_articles
from core.integrations.supabase.auth import get_current_user
from core.common.log import logger
from core.common.runtime_settings import runtime_settings
from schemas import success_response, error_response, WeChatAccountGroupCreate
from jobs.article import UpdateArticle

router = APIRouter(prefix="/wechat-account-groups", tags=["公众号分组管理"])


def _extract_wechat_account_ids(raw_mps: object) -> list[str]:

    if raw_mps is None:
        return []
    payload = raw_mps
    if isinstance(raw_mps, str):
        text = raw_mps.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except Exception:
            return []
    if not isinstance(payload, list):
        return []
    ids: list[str] = []
    for item in payload:
        if isinstance(item, dict):
            v = item.get("id") or item.get("wechat_account_id")
            if v:
                ids.append(str(v))
        elif item:
            ids.append(str(item))
    return sorted(set(ids))


def _to_api_group(group: dict, account_ids: list[str] | None = None) -> dict:

    item = dict(group or {})
    item["intro"] = item.get("description") or ""
    item["cover"] = item.get("cover") or ""
    item["status"] = item.get("status", 1)
    ids = account_ids if account_ids is not None else []
    item["wechat_account_ids"] = json.dumps(ids, ensure_ascii=False)
    item["wechat_account_count"] = len(ids)
    return item


def _last_sync_epoch(account: dict) -> int:
    if account.get("update_time") is not None:
        try:
            return int(account.get("update_time") or 0)
        except Exception:
            return 0
    if account.get("last_fetch"):
        try:
            dt = datetime.fromisoformat(str(account.get("last_fetch")).replace("Z", "+00:00"))
            return int(dt.timestamp())
        except Exception:
            return 0
    return 0


def _collect_group_accounts(accounts: list[dict], start_page: int, end_page: int):
    for account in accounts:
        account_id = account.get("id")
        try:
            collect_wechat_account_articles(
                account,
                on_article=UpdateArticle,
                start_page=start_page,
                max_page=end_page,
            )
        except Exception as e:
            logger.error(f"[wechat-account-group-sync] account_id={account_id} failed: {e}")


@router.get("", summary="获取公众号分组列表", description="分页获取所有公众号分组信息")
async def list_wechat_account_groups(
    offset: int = 0,
    limit: int = 100,
    _current_user: dict = Depends(get_current_user),
):
    """获取公众号分组列表"""
    try:
        total = await wechat_account_group_repo.count_groups()
        groups = await wechat_account_group_repo.get_groups(limit=limit, offset=offset)
        items = []
        for group in groups:
            group_id = str((group or {}).get("id") or "")
            account_ids = (
                await wechat_account_group_repo.get_wechat_account_ids_by_group(
                    group_id
                )
                if group_id
                else []
            )
            items.append(_to_api_group(group, account_ids))
        return success_response(
            data={
                "list": items,
                "page": {"limit": limit, "offset": offset, "total": total},
                "total": total,
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=500, message=f"获取公众号分组列表失败: {str(e)}"
            ),
        )


@router.post("", summary="创建新公众号分组", description="创建一个新的公众号分组")
async def create_wechat_account_group(
    group: WeChatAccountGroupCreate,
    _current_user: dict = Depends(get_current_user),
):
    """创建新公众号分组"""

    try:
        description = group.intro or None
        if not description:
            description = getattr(group, "description", None)
        group_data = {
            "name": group.name or "",
            "description": description or "",
            "cover": group.cover or "",
            "status": group.status if group.status is not None else 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        new_group = await wechat_account_group_repo.create_group(group_data)
        group_id = str((new_group or {}).get("id") or "")
        account_ids = _extract_wechat_account_ids(group.wechat_account_ids)
        bound_rows = []
        if group_id:
            bound_rows = await wechat_account_group_repo.replace_wechat_account_groups(
                group_id, account_ids
            )
        data = _to_api_group(new_group, account_ids)
        data["bound_wechat_account_count"] = len(bound_rows)
        return success_response(data=data)
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message=f"创建公众号分组失败: {str(e)}",
            ),
        )


@router.get(
    "/{group_id}",
    summary="获取单个公众号分组详情",
    description="根据ID获取公众号分组详情",
)
async def get_wechat_account_group(
    group_id: str,
    _current_user: dict = Depends(get_current_user),
):
    """获取单个公众号分组详情"""
    group = await wechat_account_group_repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(code=404, message="Tag not found"),
        )
    account_ids = await wechat_account_group_repo.get_wechat_account_ids_by_group(
        group_id
    )
    return success_response(data=_to_api_group(group, account_ids))


@router.put(
    "/{group_id}",
    summary="更新公众号分组信息",
    description="根据ID更新公众号分组信息",
)
async def update_wechat_account_group(
    group_id: str,
    group_data: WeChatAccountGroupCreate,
    _current_user: dict = Depends(get_current_user),
):
    """更新公众号分组信息"""
    try:
        existing_group = await wechat_account_group_repo.get_group_by_id(group_id)
        if not existing_group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=404, message="Tag not found"),
            )

        description = group_data.intro or None
        if not description:
            description = getattr(group_data, "description", None)
        update_data = {
            "name": group_data.name,
            "description": description or "",
            "cover": group_data.cover or "",
            "status": group_data.status if group_data.status is not None else 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        updated_groups = await wechat_account_group_repo.update_group(
            group_id, update_data
        )
        account_ids = _extract_wechat_account_ids(group_data.wechat_account_ids)
        bound_rows = await wechat_account_group_repo.replace_wechat_account_groups(
            group_id, account_ids
        )
        if updated_groups:
            data = _to_api_group(updated_groups[0], account_ids)
            data["bound_wechat_account_count"] = len(bound_rows)
            return success_response(data=data)
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_response(code=500, message="更新公众号分组失败"),
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(code=400, message=str(e)),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=500, message=str(e)),
        )


@router.delete(
    "/{group_id}",
    summary="删除公众号分组",
    description="根据ID删除公众号分组",
)
async def delete_wechat_account_group(
    group_id: str,
    _current_user: dict = Depends(get_current_user),
):
    """删除公众号分组"""
    try:
        existing_group = await wechat_account_group_repo.get_group_by_id(group_id)
        if not existing_group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=404, message="Tag not found"),
            )
        await wechat_account_group_repo.delete_group(group_id)
        return success_response(message="Tag deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=500, message=f"删除公众号分组失败: {str(e)}"),
        )


@router.post("/{group_id}/sync", summary="按公众号分组采集文章")
async def sync_wechat_account_group_articles(
    group_id: str,
    payload: dict | None = Body(None),
    _current_user: dict = Depends(get_current_user),
):
    try:
        group = await wechat_account_group_repo.get_group_by_id(group_id)
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=404, message="公众号分组不存在"),
            )

        start_page = int((payload or {}).get("start_page", 0) or 0)
        end_page = int((payload or {}).get("end_page", 1) or 1)
        if start_page < 0 or end_page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=400, message="采集页码参数不合法"),
            )

        account_ids = await wechat_account_group_repo.get_wechat_account_ids_by_group(group_id)
        if not account_ids:
            return success_response(
                {
                    "group_id": group_id,
                    "account_count": 0,
                    "started_account_ids": [],
                    "skipped_accounts": [],
                },
                message="该分组暂无公众号",
            )

        accounts = await wechat_account_repo.get_wechat_accounts_by_ids(account_ids)
        sync_interval = await runtime_settings.get_int("sync_interval", 60)
        now_epoch = int(time.time())
        runnable: list[dict] = []
        skipped: list[dict] = []

        for account in accounts:
            account_id = str(account.get("id") or "")
            if account.get("status") == 0:
                skipped.append({"id": account_id, "reason": "disabled"})
                continue
            time_span = now_epoch - _last_sync_epoch(account)
            if time_span < sync_interval:
                skipped.append(
                    {
                        "id": account_id,
                        "reason": "cooldown",
                        "time_span": time_span,
                    }
                )
                continue
            runnable.append(account)

        if runnable:
            threading.Thread(
                target=_collect_group_accounts,
                args=(runnable, start_page, end_page),
                daemon=True,
            ).start()

        return success_response(
            {
                "group_id": group_id,
                "account_count": len(accounts),
                "started_account_ids": [str(item.get("id")) for item in runnable if item.get("id")],
                "skipped_accounts": skipped,
                "start_page": start_page,
                "end_page": end_page,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"按公众号分组采集文章失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=500, message=f"按公众号分组采集文章失败: {str(e)}"),
        )
