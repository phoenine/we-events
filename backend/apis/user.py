import asyncio
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from schemas import success_response, error_response
from core.integrations.supabase.auth import get_current_user, auth_manager
from core.profiles import profile_repo
from core.common.log import logger


router = APIRouter(prefix="/user", tags=["用户资料"])


class UpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)


@router.get("", summary="获取当前用户资料")
async def get_user_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """获取当前登录用户的信息"""
    try:
        user_id = current_user.get("id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response(code=40101, message="未登录或会话已失效"),
            )

        # 从 profiles 仓储中获取扩展信息（允许不存在）
        profile = await profile_repo.get_profile_by_user_id(user_id)
        profile = profile or {}

        # 基础信息来自 Supabase Auth
        email = current_user.get("email") or ""
        username = profile.get("username") or current_user.get("username") or email
        status_value = profile.get("status") or "active"

        return success_response(
            {
                "id": user_id,
                "email": email,
                "username": username,
                "nickname": profile.get("nickname")
                or username
                or email,
                "role": profile.get("role") or "user",
                "is_active": status_value == "active",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"获取用户信息失败: {str(e)}"),
        )


@router.put("", summary="更新当前用户资料")
async def update_user_info(
    payload: UpdateUserRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        user_id = str(current_user.get("id") or "")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response(code=40101, message="未登录或会话已失效"),
            )

        profile_patch: Dict[str, Any] = {}
        if payload.username is not None:
            profile_patch["username"] = payload.username.strip()
        if payload.nickname is not None:
            profile_patch["nickname"] = payload.nickname.strip()
        if payload.is_active is not None:
            profile_patch["status"] = "active" if payload.is_active else "disabled"
        if profile_patch:
            await profile_repo.upsert_profile(user_id, profile_patch)

        # 尝试同步 Supabase Auth 用户邮箱。业务用户名/角色/状态保存在 profiles。
        # 失败时不阻断 profile 更新，避免前端“保存失败但实际已保存”的体验问题。
        email = (payload.email or "").strip() if payload.email is not None else None
        if email is not None:
            try:
                service_client = auth_manager.get_client(use_service=True)
                update_data: Dict[str, Any] = {}
                if email:
                    update_data["email"] = email
                if update_data:
                    await asyncio.to_thread(
                        service_client.auth.admin.update_user_by_id,
                        user_id,
                        update_data,
                    )
            except Exception as sync_err:
                logger.warning(f"用户资料已更新，但 Auth 字段同步失败: {sync_err}")

        return success_response(message="用户信息更新成功")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"更新用户信息失败: {str(e)}"),
        )


@router.put("/password", summary="修改当前用户密码")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        email = (current_user or {}).get("email")
        user_id = (current_user or {}).get("id")
        if not email or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response(code=40101, message="未登录或会话已失效"),
            )

        if payload.old_password == payload.new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(code=40001, message="新密码不能与旧密码相同"),
            )

        # 校验旧密码
        await auth_manager.sign_in(email, payload.old_password)

        # 使用 service role 直接更新密码
        service_client = auth_manager.get_client(use_service=True)
        await asyncio.to_thread(
            service_client.auth.admin.update_user_by_id,
            str(user_id),
            {"password": payload.new_password},
        )
        return success_response(message="密码修改成功")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"修改密码失败: {str(e)}"),
        )
