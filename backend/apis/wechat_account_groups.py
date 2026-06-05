import json
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timezone
from core.wechat_account_groups import wechat_account_group_repo
from core.integrations.supabase.auth import get_current_user
from core.common.log import logger
from schemas import success_response, error_response, WeChatAccountGroupCreate

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
    return item


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
