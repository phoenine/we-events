import platform
import time
import sys
from fastapi import APIRouter, Depends, HTTPException, status
from schemas import success_response, error_response, API_VERSION
from core.integrations.supabase.auth import get_current_user
from core.common.app_settings import settings
from core.common.base import VERSION as CORE_VERSION, LATEST_VERSION
from core.common.resource import get_system_resources
from core.articles.lax import laxArticle
from core.jobs import TaskQueue
from driver.wx.service import (
    get_state as wx_get_state,
    get_session_info as wx_get_session_info,
)
from driver.wx.state import LoginState

router = APIRouter(prefix="/sys", tags=["系统信息"])

# 记录服务器启动时间
_START_TIME = time.time()


@router.get("/base_info", summary="常规信息")
async def get_base_info():
    try:
        base_info = {
            "api_version": API_VERSION,
            "core_version": CORE_VERSION,
            "ui": {
                "name": settings.server_name,
                "web_name": settings.web_name,
            },
        }
        return success_response(data=base_info)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"获取信息失败: {str(e)}"),
        ) from e


@router.get("/resources", summary="获取系统资源使用情况")
async def system_resources(
    current_user: dict = Depends(get_current_user),
):
    """获取系统资源使用情况

    Returns:
        BaseResponse格式的资源使用信息, 包括:
        - cpu: CPU使用率(%)
        - memory: 内存使用情况
        - disk: 磁盘使用情况
    """
    try:
        resources_info = get_system_resources()
        resources_info["queue"] = TaskQueue.get_queue_info()
        return success_response(data=resources_info)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50002, message=f"获取系统资源失败: {str(e)}"),
        ) from e


@router.get("/info", summary="获取系统信息")
async def get_system_info(
    current_user: dict = Depends(get_current_user),
):
    """获取当前系统的各种信息

    Returns:
        BaseResponse格式的系统信息，包括:
        - os: 操作系统信息
        - python_version: Python版本
        - uptime: 服务器运行时间(秒)
        - system: 系统详细信息
    """
    try:
        system_info = {
            "os": {
                "name": platform.system(),
                "version": platform.version(),
                "release": platform.release(),
            },
            "python_version": sys.version,
            "uptime": round(time.time() - _START_TIME, 2),
            "system": {
                "node": platform.node(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            },
            "api_version": API_VERSION,
            "core_version": CORE_VERSION,
            "latest_version": LATEST_VERSION,
            "need_update": CORE_VERSION != LATEST_VERSION,
            "wx": {
                "login": wx_get_state().get("state") == LoginState.SUCCESS.value,
                "session": (
                    wx_get_session_info().get("session")
                    if isinstance(wx_get_session_info(), dict)
                    else None
                ),
            },
            "article": laxArticle(),
            "queue": TaskQueue.get_queue_info(),
        }
        return success_response(data=system_info)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"获取系统信息失败: {str(e)}"),
        ) from e
