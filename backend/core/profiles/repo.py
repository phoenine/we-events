from typing import Any, Dict, Optional


class ProfilesRepository:
    """profiles 表仓储类"""

    TABLE_NAME = "profiles"

    def __init__(self, client: Any) -> None:
        """接收一个 Supabase v2 Client 实例"""
        self.client = client

    async def get_profile_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """根据 Supabase Auth 的 user_id 获取 profile 记录"""
        rows = await self.client.select(
            self.TABLE_NAME,
            filters={"user_id": user_id},
            limit=1,
        )
        return rows[0] if rows else None

    async def upsert_profile(self, user_id: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """按 user_id 合并更新 profile 字段。"""
        payload: Dict[str, Any] = {"user_id": user_id, **(profile_data or {})}
        rows = await self.client.upsert(
            self.TABLE_NAME,
            payload,
            on_conflict="user_id",
        )
        return rows[0] if rows else payload
