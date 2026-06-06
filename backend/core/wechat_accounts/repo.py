from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from core.common.utils.async_tools import run_sync


class WeChatAccountRepository:

    TABLE_NAME = "wechat_accounts"

    def __init__(self, client: Any):
        self.client = client

    async def get_wechat_accounts(
        self,
        filters: Optional[Dict] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: str = "created_at.desc",
    ):
        """获取公众号账号列表（通用过滤）"""
        return await self.client.select(
            self.TABLE_NAME, filters=filters, limit=limit, offset=offset, order=order_by
        )

    async def get_wechat_accounts_by_status(
        self,
        status: int,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: str = "created_at.desc",
    ):
        """根据状态获取公众号账号列表（便捷方法）"""
        filters = {"status": status}
        return await self.get_wechat_accounts(
            filters=filters, limit=limit, offset=offset, order_by=order_by
        )

    async def get_wechat_account_by_id(self, account_id: str):
        """根据 ID 获取公众号账号"""
        accounts = await self.client.select(self.TABLE_NAME, filters={"id": account_id})
        return accounts[0] if accounts else None

    async def get_wechat_accounts_by_ids(self, account_ids: List[str]):
        """根据 ID 列表获取公众号账号"""
        return await self.client.select(self.TABLE_NAME, filters={"id": {"in": account_ids}})

    async def get_wechat_account_by_faker_id(self, faker_id: str):
        """根据 faker_id 获取公众号账号"""
        accounts = await self.client.select(self.TABLE_NAME, filters={"faker_id": faker_id})
        return accounts[0] if accounts else None

    async def get_wechat_account_by_identity(
        self, *, account_id: Optional[str] = None, faker_id: Optional[str] = None
    ):
        """根据公众号稳定标识获取账号，优先系统 id，其次微信 fakeid。"""
        if account_id:
            account = await self.get_wechat_account_by_id(account_id)
            if account:
                return account
        if faker_id:
            return await self.get_wechat_account_by_faker_id(faker_id)
        return None

    async def count_wechat_accounts(self, filters: Optional[Dict] = None):
        """统计公众号账号数量"""
        return await self.client.count(self.TABLE_NAME, filters=filters)

    async def create_wechat_account(self, account_data: Dict):
        """创建公众号账号"""
        return await self.client.insert(self.TABLE_NAME, account_data)

    async def update_wechat_account(self, account_id: str, account_data: Dict):
        """更新公众号账号"""
        return await self.client.update(self.TABLE_NAME, account_data, filters={"id": account_id})

    async def delete_wechat_account(self, account_id: str):
        """删除公众号账号"""
        return await self.client.delete(
            self.TABLE_NAME,
            filters={"id": account_id},
        )

    def sync_get_wechat_accounts_by_ids(self, account_ids: List[str]):
        """同步根据 ID 列表获取公众号账号。"""
        return run_sync(self.get_wechat_accounts_by_ids(account_ids))

    def sync_update_wechat_account(self, account_id: str, account_data: Dict):
        """同步更新公众号账号。"""
        return run_sync(self.update_wechat_account(account_id, account_data))

    def sync_count_wechat_accounts(self, filters: Optional[Dict] = None):
        """同步统计公众号账号数量。"""
        return run_sync(self.count_wechat_accounts(filters=filters))

    def sync_get_wechat_accounts(
        self,
        filters: Optional[Dict] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: str = "created_at.desc",
    ):
        """同步获取公众号账号列表。"""
        return run_sync(
            self.get_wechat_accounts(
                filters=filters, limit=limit, offset=offset, order_by=order_by
            )
        )
