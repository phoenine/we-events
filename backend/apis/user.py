import os
import re
from typing import Dict, Any
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel, Field
from schemas import success_response, error_response
from core.integrations.supabase.auth import get_current_user, auth_manager
from core.profiles import profile_repo
from core.integrations.supabase.storage import supabase_storage_avatar
from core.common.runtime_settings import runtime_settings
from core.common.log import logger


router = APIRouter(prefix="/user", tags=["用户资料"])


class UpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, max_length=100)
    nickname: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=255)
    avatar: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)


def _extract_avatar_object_path(value: str) -> str:
    """
    从数据库中保存的头像值解析对象路径。
    兼容三种格式：
    1) 纯对象路径（avatar/xx.png 或 avatars/xx.png）
    2) public URL（.../storage/v1/object/public/{bucket}/{path}）
    3) signed URL（.../storage/v1/object/sign/{bucket}/{path}?token=...）
    """
    raw = (value or "").strip()
    if not raw:
        return ""

    if raw.startswith("http://") or raw.startswith("https://"):
        public_prefix = f"/storage/v1/object/public/{supabase_storage_avatar.bucket}/"
        sign_prefix = f"/storage/v1/object/sign/{supabase_storage_avatar.bucket}/"
        if public_prefix in raw:
            return raw.split(public_prefix, 1)[1].split("?", 1)[0]
        if sign_prefix in raw:
            return raw.split(sign_prefix, 1)[1].split("?", 1)[0]
    return raw


async def _resolve_avatar_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    obj_path = _extract_avatar_object_path(raw)
    if not obj_path:
        return raw

    # 优先返回 signed URL，兼容私有 bucket；失败再回退 public URL。
    try:
        return await supabase_storage_avatar.sign_url(obj_path, expires=7 * 24 * 3600)
    except Exception:
        return supabase_storage_avatar.public_url(obj_path)


def _render_storage_path(template: str, values: dict[str, str]) -> str:
    """渲染 storage 路径模板，避免因占位符不一致导致 KeyError。"""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in values:
            return str(values[key])
        return str(values.get("uuid", uuid4().hex))

    return re.sub(r"\{([a-zA-Z0-9_]+)\}", replace, template)


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
                "avatar": await _resolve_avatar_url(profile.get("avatar_path") or ""),
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


@router.post("/avatar", summary="上传用户头像")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """处理用户头像上传"""
    try:
        allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=error_response(code=41501, message="不支持的头像类型"),
            )

        # 默认限制 5MB，可通过配置 avatar.max_bytes 覆盖
        max_bytes = await runtime_settings.get_int("avatar.max_bytes", 5 * 1024 * 1024)
        file_bytes = bytearray()
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            file_bytes.extend(chunk)
            if len(file_bytes) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=error_response(code=41301, message="头像文件过大"),
                )
        _, ext = os.path.splitext(file.filename or "")
        if not ext:
            ext = ".jpg"
        user_id = str(current_user.get("id") or "")
        username = str(current_user.get("username") or user_id or "user")
        object_path = _render_storage_path(
            supabase_storage_avatar.path,
            {
                "uuid": str(uuid4()),
                "user_id": user_id,
                "username": username,
                "filename": file.filename or f"{username}{ext}",
            },
        )

        _ = await supabase_storage_avatar.upload_bytes(
            data=bytes(file_bytes),
            path=object_path,
            content_type=file.content_type or "image/jpeg",
        )

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response(code=40101, message="未登录或会话已失效"),
            )

        # 存储对象路径，避免把不稳定的 URL（域名/公网策略）固化到数据库
        await profile_repo.update_avatar(user_id, object_path)
        return success_response(data={"avatar": await _resolve_avatar_url(object_path)})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"头像上传失败: {str(e)}",
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
        if payload.avatar is not None:
            profile_patch["avatar_path"] = _extract_avatar_object_path(payload.avatar)
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
                    service_client.auth.admin.update_user_by_id(user_id, update_data)
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
        service_client.auth.admin.update_user_by_id(
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


# TODO: 本地文件上传接口，暂时弃用
# @router.post("/upload", summary="上传文件")
# async def upload_file(
#     file: UploadFile = File(...),
#     type: str = "tags",
#     current_user: dict = Depends(get_current_user),
# ):
#     """处理用户文件上传"""
#     try:
#         # 验证 type 参数的安全性
#         if not type.isalnum() or type in ["", ".."]:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=error_response(code=40003, message="无效的文件类型"),
#             )
#         file_url_path = f"files/{type}/"
#         from core.res.avatar import files_dir
#
#         upload_path = f"{files_dir}/{type}/"
#         # 确保上传目录存在
#         os.makedirs(upload_path, exist_ok=True)
#
#         # 生成唯一的文件名
#         file_name = f"{current_user['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
#         file_path = f"{upload_path}/{file_name}"
#
#         # 保存文件
#         with open(file_path, "wb") as buffer:
#             buffer.write(await file.read())
#         return success_response(data={"url": f"/{file_url_path}/{file_name}"})
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_406_NOT_ACCEPTABLE, detail=f"文件上传失败: {str(e)}"
#         )
