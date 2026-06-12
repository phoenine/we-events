import os
from typing import Optional, Dict, Any
import httpx

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    OAuth2PasswordBearer,
    HTTPBearer,
    HTTPAuthorizationCredentials,
)
from supabase import create_client, Client
from pydantic import BaseModel

from core.integrations.supabase.settings import settings
from core.auth.model import UserCredentials, TokenResponse
from core.common.log import logger

# Supabase 配置
SUPABASE_URL = settings.url
SUPABASE_ANON_KEY = settings.anon_key
SUPABASE_SERVICE_KEY = settings.service_key

# OAuth2 配置（用于 /api/v1/wx/auth/token 密码登录模式）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/wx/auth/token", auto_error=False)
security = HTTPBearer(auto_error=False)


class SupabaseAuthManager:
    """Supabase 认证管理器"""

    def __init__(self) -> None:
        self.url: str = SUPABASE_URL
        self.anon_key: str = SUPABASE_ANON_KEY
        self.service_key: str = SUPABASE_SERVICE_KEY
        self.client: Optional[Client] = None
        self.service_client: Optional[Client] = None
        self._initialized: bool = False

    def init(self) -> None:
        """初始化 Supabase 客户端"""
        if not self.url or not self.anon_key:
            raise ValueError("SUPABASE_URL 和 SUPABASE_ANON_KEY 环境变量必须设置")

        if self._initialized and self.client is not None:
            return

        try:
            # 匿名客户端（用于用户登录注册）
            self.client = create_client(self.url, self.anon_key)

            # 服务客户端（用于管理员操作）
            if self.service_key:
                self.service_client = create_client(self.url, self.service_key)

            self._initialized = True
            logger.info("Supabase 认证客户端初始化成功")

        except Exception as e:
            logger.error(f"Supabase 认证客户端初始化失败: {e}")
            raise

    def get_client(self, use_service: bool = False) -> Client:
        """获取 Supabase 客户端"""
        if not self._initialized or (
            not self.client and not (use_service and self.service_client)
        ):
            self.init()

        if use_service:
            if self.service_client is None:
                raise RuntimeError("Supabase 服务客户端尚未成功初始化")
            return self.service_client

        if self.client is None:
            raise RuntimeError("Supabase 匿名客户端尚未成功初始化")

        return self.client

    async def sign_up(
        self,
        email: str,
        password: str,
        user_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """用户注册（使用 Supabase Auth）

        - email: 用户邮箱
        - password: 登录密码
        - user_metadata: 额外的用户元数据（如 role、username 等），会写入 Supabase Auth 的 user_metadata
        """
        try:
            client = self.get_client()

            # 组装 user_metadata：调用方传入的元数据优先，缺失时自动补充 username
            metadata: Dict[str, Any] = dict(user_metadata or {})
            if "username" not in metadata:
                # 默认使用邮箱前缀作为 username
                metadata["username"] = email.split("@")[0]

            # 注册用户（依赖 Supabase Auth）
            auth_response = client.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {
                        "data": metadata,
                    },
                }
            )

            if auth_response.user:
                logger.info(f"用户注册成功: {email}")
                return {
                    "user": auth_response.user,
                    "session": auth_response.session,
                }

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户注册失败",
            )

        except HTTPException:
            # 保持上层 HTTP 状态码不变
            raise
        except Exception as e:
            logger.error(f"用户注册失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"用户注册失败: {str(e)}",
            )

    async def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """用户登录（邮箱 + 密码）"""
        try:
            client = self.get_client()

            # 用户登录
            auth_response = client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )

            if auth_response.user and auth_response.session:
                logger.info(f"用户登录成功: {email}")
                return {"user": auth_response.user, "session": auth_response.session}

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="邮箱或密码错误",
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"用户登录失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"登录失败: {str(e)}",
            )

    async def sign_out(self, token: str) -> bool:
        """用户登出（当前为无状态 token，后端不维护会话，仅作占位）"""
        # 对于基于 Supabase Access Token 的无状态认证，后端通常不需要显式注销，
        # 前端丢弃 token 即可视为登出。此方法保留以便未来扩展（如服务端记录黑名单等）。
        try:
            logger.info("用户登出请求已接收（无状态认证，未在服务端维护会话）")
            return True
        except Exception as e:
            logger.error(f"用户登出处理异常: {e}")
            return False

    async def get_user_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"{self.url}/auth/v1/user",
                        headers={"apikey": self.anon_key, "Authorization": f"Bearer {token}"},
                    )
                if resp.status_code != 200:
                    logger.warning(f"auth verify attempt {attempt+1}/{MAX_RETRIES} status={resp.status_code}")
                    if attempt < MAX_RETRIES - 1:
                        import asyncio
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    return None
                user_data = resp.json()
                if not user_data or not user_data.get("id"):
                    return None

                profile = {}
                try:
                    svc = self.get_client(use_service=True)
                    rows = (svc.table("profiles").select("username,nickname,role,status")
                            .eq("user_id", str(user_data["id"])).limit(1).execute()).data
                    profile = rows[0] if rows else {}
                except Exception as ex:
                    logger.warning(f"profile read failed: {ex}")

                if (profile.get("status") or "active") != "active":
                    return None

                return {
                    "id": str(user_data["id"]),
                    "email": user_data.get("email"),
                    "username": profile.get("username") or user_data.get("user_metadata", {}).get("username") or user_data.get("email"),
                    "nickname": profile.get("nickname"),
                    "role": profile.get("role") or "user",
                    "status": profile.get("status") or "active",
                }

            except Exception as e:
                logger.warning(f"auth verify exception attempt {attempt+1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    import asyncio
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                return None
        return None

    async def refresh_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """刷新访问令牌"""
        try:
            client = self.get_client()

            # 刷新 token（具体调用根据 Supabase Python SDK 版本可能略有不同）
            auth_response = client.auth.refresh_session(refresh_token)

            if auth_response.session:
                return {
                    "access_token": auth_response.session.access_token,
                    "refresh_token": auth_response.session.refresh_token,
                    "expires_in": auth_response.session.expires_in,
                    "user": auth_response.user,
                }

            return None

        except Exception as e:
            logger.error(f"Token 刷新失败: {e}")
            return None


# 全局认证管理器实例
auth_manager = SupabaseAuthManager()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> Dict[str, Any]:
    """获取当前用户（必须登录）"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await auth_manager.get_user_by_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    token: str = Depends(oauth2_scheme),
) -> Optional[Dict[str, Any]]:
    """可选地获取当前用户（未登录时返回 None）"""
    if not token:
        return None

    # get_user_by_token 内部已处理异常并返回 None，这里不再二次捕获
    return await auth_manager.get_user_by_token(token)


async def authenticate_user_credentials(
    credentials: UserCredentials,
):
    """验证用户凭据并返回 token（仅支持用户名/密码登录，这里的用户名即邮箱）"""
    try:
        # 这里将 username 视为登录邮箱，由前端约定使用 email 作为登录名
        auth_result = await auth_manager.sign_in(
            credentials.username,
            credentials.password,
        )

        session = auth_result["session"]
        user = auth_result["user"]

        return TokenResponse(
            access_token=session.access_token,
            token_type="bearer",
            expires_in=session.expires_in,
            user={
                "id": str(user.id),
                "email": user.email,
                "username": user.user_metadata.get(
                    "username",
                    user.email,
                ),
            },
        )

    except HTTPException:
        # 透传上游明确的认证错误（如邮箱或密码错误）
        raise
    except Exception as e:
        logger.error(f"用户认证失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"认证失败: {str(e)}",
        )
