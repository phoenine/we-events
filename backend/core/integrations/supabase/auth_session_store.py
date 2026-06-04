import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from core.common.log import logger
from core.common.utils.async_tools import run_sync
from core.integrations.supabase.client import supabase_client
from core.integrations.supabase.settings import settings



class AuthSessionStore:
    """公众号扫码认证会话存储。"""

    SESSION_TABLE = "wechat_auth_sessions"
    SECRET_TABLE = "wechat_auth_session_secret"

    def __init__(self):
        self.client = supabase_client
        self.user_id = os.getenv("SUPABASE_USER_ID")

    def valid_session_db(self):
        """检查会话数据库是否可用"""
        return bool(settings.url and settings.service_key)

    async def create_session(
        self, user_id: Optional[str] = None, expires_minutes: int = 2
    ):
        """创建认证会话"""
        if not self.valid_session_db():
            return None

        sid = str(uuid.uuid4())
        uid = user_id or self.user_id
        if not uid:
            return sid  # 返回生成的会话ID，但不落库

        try:
            await self.client.insert(
                self.SESSION_TABLE,
                {
                    "id": sid,
                    "maintained_by": uid,
                    "status": "waiting",
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
                    ).isoformat(),
                },
            )
            return sid
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            return sid  # 仍然返回会话ID，但记录错误

    async def update_session(
        self,
        session_id: str,
        status: Optional[str] = None,
        qr_path: Optional[str] = None,
        qr_signed_url: Optional[str] = None,
        expires_minutes: Optional[int] = None,
    ):
        """更新会话信息"""
        if not self.valid_session_db() or not session_id:
            return False

        sets = []
        vals = []
        if status:
            sets.append("status=%s")
            vals.append(status)
        if qr_path:
            sets.append("qr_path=%s")
            vals.append(qr_path)
        if qr_signed_url:
            sets.append("qr_signed_url=%s")
            vals.append(qr_signed_url)
        if expires_minutes is not None:
            sets.append("expires_at=%s")
            vals.append(
                (
                    datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
                ).isoformat()
            )
        if not sets:
            return False

        try:
            payload = dict(zip([s.split("=")[0] for s in sets], vals))
            logger.info(
                f"[auth-session-store] update session_id={session_id} payload={payload}"
            )
            await self.client.update(
                self.SESSION_TABLE,
                payload,
                filters={"id": session_id},
            )
            return True
        except Exception as e:
            logger.error(f"更新会话失败: {e}")
            return False

    def update_session_sync(
        self,
        session_id: str,
        status: Optional[str] = None,
        qr_path: Optional[str] = None,
        qr_signed_url: Optional[str] = None,
        expires_minutes: Optional[int] = None,
    ):
        return run_sync(
            self.update_session(
                session_id=session_id,
                status=status,
                qr_path=qr_path,
                qr_signed_url=qr_signed_url,
                expires_minutes=expires_minutes,
            )
        )

    async def write_secret(
        self,
        session_id: str,
        token: str,
        cookies_str: str,
        expiry_ts: Optional[float] = None,
    ):
        """写入会话密钥"""
        if not self.valid_session_db() or not session_id:
            return False
        expires_at = (
            datetime.fromtimestamp(expiry_ts, tz=timezone.utc) if expiry_ts else None
        )
        try:
            await self.client.upsert(
                self.SECRET_TABLE,
                {
                    "session_id": session_id,
                    "token": token or "",
                    "cookies_str": cookies_str or "",
                    "expiry": expires_at.isoformat() if expires_at else None,
                },
                on_conflict="session_id",
            )
            return True
        except Exception as e:
            logger.error(f"写入会话密钥失败: {e}")
            return False

    def write_secret_sync(
        self,
        session_id: str,
        token: str,
        cookies_str: str,
        expiry_ts: Optional[float] = None,
    ):
        return run_sync(
            self.write_secret(
                session_id=session_id,
                token=token,
                cookies_str=cookies_str,
                expiry_ts=expiry_ts,
            )
        )


auth_session_store = AuthSessionStore()
