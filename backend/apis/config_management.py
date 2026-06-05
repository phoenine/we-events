from fastapi import APIRouter, Depends, HTTPException, Body, Path, Query, status

from core.integrations.supabase.auth import get_current_user
from core.integrations.supabase.config_store import config_store
from schemas import success_response, error_response, ConfigManagementCreate


router = APIRouter(prefix="/configs", tags=["配置管理"])


@router.get("", summary="获取配置项列表")
async def list_configs(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _current_user: dict = Depends(get_current_user),
):
    """获取配置项列表"""
    try:
        total = await config_store.count()
        paginated_configs = await config_store.fetch_all(limit=limit, offset=offset)

        return success_response(
            data={
                "list": paginated_configs,
                "page": {"limit": limit, "offset": offset},
                "total": total,
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=500, message=str(e)),
        )


@router.get("/{config_key}", summary="获取单个配置项详情")
async def get_config(
    config_key: str,
    _current_user: dict = Depends(get_current_user),
):
    """获取单个配置项详情"""
    try:
        row = await config_store.get(config_key)
        if not row:
            raise HTTPException(status_code=404, detail="Config not found")
        return success_response(data=row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=500, message=str(e)),
        )


@router.post("", summary="创建配置项")
async def create_config(
    config_data: ConfigManagementCreate = Body(...),
    _current_user: dict = Depends(get_current_user),
):
    """创建配置项"""
    try:
        existing = await config_store.get(config_data.config_key)
        if existing:
            raise HTTPException(
                status_code=400, detail="Config with this key already exists"
            )

        created = await config_store.create(
            config_key=config_data.config_key,
            config_value=config_data.config_value,
            description=config_data.description or "系统配置项",
        )
        return success_response(data=created)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=500, message=str(e)),
        )


@router.put("/{config_key}", summary="更新配置项")
async def update_config(
    config_key: str = Path(..., min_length=1),
    config_data: ConfigManagementCreate = Body(...),
    _current_user: dict = Depends(get_current_user),
):
    """更新配置项"""
    try:
        existing = await config_store.get(config_key)
        if not existing:
            raise HTTPException(status_code=404, detail="Config not found")

        updated = await config_store.update(
            config_key=config_key,
            config_value=config_data.config_value,
            description=config_data.description,
        )
        return success_response(data=updated)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=500, message=str(e)),
        )


@router.delete("/{config_key}", summary="删除配置项")
async def delete_config(
    config_key: str,
    _current_user: dict = Depends(get_current_user),
):
    """删除配置项"""
    try:
        deleted = await config_store.delete(config_key)
        if not deleted:
            raise HTTPException(status_code=404, detail="Config not found")
        return success_response(data={"config_key": config_key, "deleted": True})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=500, message=str(e)),
        )
