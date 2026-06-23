from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any


class WeChatAccountGroupRepository:

    GROUP_TABLE = "wechat_account_groups"
    WECHAT_ACCOUNT_TABLE = "wechat_accounts"

    def __init__(self, client: Any):
        self.client = client

    @staticmethod
    def _as_group_int(group_id: str | int) -> int:
        return int(str(group_id).strip())

    async def get_groups(self, limit: Optional[int] = None, offset: Optional[int] = None):
        """获取所有公众号分组"""
        return await self.client.select(
            self.GROUP_TABLE, limit=limit, offset=offset, order="name.asc"
        )

    async def get_wechat_account_ids_by_group(self, group_id: str) -> List[str]:
        """获取公众号分组关联的公众号 ID 列表。"""
        group_id_int = self._as_group_int(group_id)
        rows = await self.client.select(
            self.WECHAT_ACCOUNT_TABLE,
            filters={"group_id": group_id_int},
            order="created_at.asc",
        )
        return [str(r.get("id")) for r in rows if r.get("id")]

    async def replace_wechat_account_groups(self, group_id: str, account_ids: List[str]):
        """按公众号分组替换公众号关联关系（一对多：wechat_accounts.group_id）。"""
        group_id_int = self._as_group_int(group_id)
        # 先解绑当前公众号分组下的所有公众号账号
        await self.client.update(
            self.WECHAT_ACCOUNT_TABLE,
            {"group_id": None},
            filters={"group_id": group_id_int},
        )
        ids = [str(i).strip() for i in (account_ids or []) if str(i).strip()]
        if not ids:
            return []
        existing_rows = await self.client.select(
            self.WECHAT_ACCOUNT_TABLE,
            filters={"id": {"in": sorted(set(ids))}},
            columns="id",
        )
        existing_ids = {str(r.get("id")) for r in existing_rows if r.get("id")}
        if not existing_ids:
            raise ValueError("所选公众号ID不存在，无法绑定公众号分组")
        updated = []
        for fid in sorted(existing_ids):
            rows = await self.client.update(
                self.WECHAT_ACCOUNT_TABLE,
                {"group_id": group_id_int},
                filters={"id": fid},
            )
            if rows:
                updated.extend(rows)
        return updated

    async def count_groups(self, filters: Optional[Dict] = None):
        """统计公众号分组数量"""
        return await self.client.count(self.GROUP_TABLE, filters=filters)

    async def get_group_by_id(self, group_id: str):
        """根据ID获取公众号分组"""
        wechat_account_groups = await self.client.select(self.GROUP_TABLE, filters={"id": group_id})
        return wechat_account_groups[0] if wechat_account_groups else None

    async def get_group_by_name(self, name: str):
        """根据名称获取公众号分组"""
        wechat_account_groups = await self.client.select(self.GROUP_TABLE, filters={"name": name})
        return wechat_account_groups[0] if wechat_account_groups else None

    async def create_group(self, group_data: Dict):
        """创建公众号分组"""
        return await self.client.insert(self.GROUP_TABLE, group_data)

    async def update_group(self, group_id: str, group_data: Dict):
        """更新公众号分组"""
        return await self.client.update(
            self.GROUP_TABLE, group_data, filters={"id": group_id}
        )

    async def update_group_schedule(
        self,
        group_id: str,
        *,
        schedule_enabled: bool,
        schedule_time: str | None,
        collection_pages: int,
    ):
        return await self.client.update(
            self.GROUP_TABLE,
            {
                "schedule_enabled": schedule_enabled,
                "schedule_time": schedule_time,
                "collection_pages": collection_pages,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            filters={"id": group_id},
        )

    async def get_enabled_schedules(self):
        return await self.client.select(
            self.GROUP_TABLE,
            filters={"schedule_enabled": True, "status": 1},
            order="id.asc",
        )

    async def mark_schedule_attempt(
        self, group_id: str, payload: dict[str, Any]
    ):
        return await self.client.update(
            self.GROUP_TABLE, payload, filters={"id": group_id}
        )

    async def delete_group(self, group_id: str):
        """删除公众号分组"""
        group_id_int = self._as_group_int(group_id)
        await self.client.update(
            self.WECHAT_ACCOUNT_TABLE,
            {"group_id": None},
            filters={"group_id": group_id_int},
        )
        result = await self.client.delete(self.GROUP_TABLE, filters={"id": group_id})
        return bool(result)
