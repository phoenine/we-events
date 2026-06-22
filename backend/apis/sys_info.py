import platform
import time
import sys
from fastapi import APIRouter, Depends, HTTPException, status
from schemas import success_response, error_response, API_VERSION
from core.integrations.supabase.auth import get_current_admin_user
from core.common.app_settings import settings
from core.common.base import VERSION as CORE_VERSION, LATEST_VERSION
from core.common.resource import get_system_resources
from core.articles.lax import laxArticle
from core.articles import article_collection_repo
from core.activities import activity_run_repo
from driver.wx.service import (
    get_state as wx_get_state,
)
from driver.wx.state import LoginState
from driver.session.manager import SessionManager

router = APIRouter(prefix="/sys", tags=["系统信息"])

# 记录服务器启动时间
_START_TIME = time.time()


async def _build_queue_status() -> dict:
    """构建数据库队列状态。"""
    try:
        article_runs_total = await article_collection_repo.count_runs()
        article_items_queued = await article_collection_repo.count_items("queued")
        article_items_processing = await article_collection_repo.count_items("processing")
        activity_runs_total = await activity_run_repo.count_runs()
        activity_runs_queued = await activity_run_repo.count_runs("queued")
        activity_runs_processing = await activity_run_repo.count_runs("processing")
        return {
            "article_collection": {
                "runs_total": article_runs_total,
                "queued_items": article_items_queued,
                "processing_items": article_items_processing,
            },
            "activity_extraction": {
                "runs_total": activity_runs_total,
                "queued_runs": activity_runs_queued,
                "processing_runs": activity_runs_processing,
            },
        }
    except Exception as e:
        return {"error": str(e)}


def _build_wx_auth_status() -> dict:
    """构建公众号授权状态，供前端直接展示。"""
    return _build_wx_auth_status_from_state(wx_get_state())


def _build_wx_auth_status_from_state(state_env: dict) -> dict:
    """基于 wx service envelope 构建公众号授权状态。"""
    state_data = state_env.get("data") if isinstance(state_env, dict) else {}
    state = str((state_data or {}).get("state") or LoginState.IDLE.value)
    error = (state_data or {}).get("error")

    manager = SessionManager()
    session = manager.load_persisted_session()
    expiry = session.get("expiry") if isinstance(session, dict) else None
    is_valid = manager.is_session_valid(session)

    expires_at = None
    remaining_seconds = None
    if isinstance(expiry, dict):
        expires_at = expiry.get("expiry_time")
        try:
            remaining_seconds = int(expiry.get("remaining_seconds") or 0)
        except Exception:
            remaining_seconds = None

    if is_valid:
        status_value = "authorized"
        label = "已授权"
        message = "公众号登录态可用"
    elif session:
        status_value = "expired"
        label = "已过期"
        message = "公众号登录态已过期，请重新扫码授权"
    elif state in (LoginState.STARTING.value, LoginState.QR_READY.value, LoginState.WAIT_SCAN.value):
        status_value = "pending"
        label = "授权中"
        message = "等待扫码确认"
    elif state == LoginState.FAILED.value:
        status_value = "error"
        label = "授权异常"
        message = str(error or "公众号授权异常，请重新扫码")
    else:
        status_value = "unauthorized"
        label = "未授权"
        message = "尚未完成公众号扫码授权"

    return {
        "status": status_value,
        "label": label,
        "message": message,
        "state": state,
        "has_session": bool(session),
        "is_valid": bool(is_valid),
        "expires_at": expires_at,
        "remaining_seconds": remaining_seconds,
        "error": error,
    }


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
    current_user: dict = Depends(get_current_admin_user),
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
        resources_info["queues"] = await _build_queue_status()
        return success_response(data=resources_info)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50002, message=f"获取系统资源失败: {str(e)}"),
        ) from e


@router.get("/info", summary="获取系统信息")
async def get_system_info(
    current_user: dict = Depends(get_current_admin_user),
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
        state_env = wx_get_state()
        state_data = state_env.get("data") if isinstance(state_env, dict) else {}
        wx_state = str((state_data or {}).get("state") or LoginState.IDLE.value)
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
                "login": wx_state == LoginState.SUCCESS.value,
                "auth": _build_wx_auth_status_from_state(state_env),
            },
            "article": laxArticle(),
            "queues": await _build_queue_status(),
        }
        return success_response(data=system_info)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"获取系统信息失败: {str(e)}"),
        ) from e
