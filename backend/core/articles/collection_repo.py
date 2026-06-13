from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ArticleCollectionRepository:
    RUN_TABLE = "article_collection_runs"
    ITEM_TABLE = "article_collection_items"

    def __init__(self, client: Any):
        self.client = client

    async def create_run(self, run_data: dict[str, Any]):
        return await self.client.insert(self.RUN_TABLE, run_data)

    async def update_run(self, run_id: str, run_data: dict[str, Any]):
        run_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.client.update(self.RUN_TABLE, run_data, filters={"id": run_id})

    async def get_run_by_id(self, run_id: str):
        rows = await self.client.select(self.RUN_TABLE, filters={"id": run_id}, limit=1)
        return rows[0] if rows else None

    async def count_runs(self, status: str | None = None):
        filters = {"status": status} if status else None
        return await self.client.count(self.RUN_TABLE, filters=filters)

    async def create_item(self, item_data: dict[str, Any]):
        return await self.client.insert(self.ITEM_TABLE, item_data)

    async def update_item(self, item_id: str, item_data: dict[str, Any]):
        item_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.client.update(self.ITEM_TABLE, item_data, filters={"id": item_id})

    async def get_items_by_run(self, run_id: str):
        return await self.client.select(
            self.ITEM_TABLE,
            filters={"run_id": run_id},
            order="created_at.asc",
        )

    async def count_items(self, status: str | None = None):
        filters = {"status": status} if status else None
        return await self.client.count(self.ITEM_TABLE, filters=filters)

    async def get_latest_active_item_by_account(self, wechat_account_id: str):
        rows = await self.client.select(
            self.ITEM_TABLE,
            filters={
                "wechat_account_id": wechat_account_id,
                "status": {"in": ["queued", "processing"]},
            },
            limit=1,
            order="created_at.desc",
        )
        return rows[0] if rows else None

    async def claim_next_item(self, *, worker_id: str, stale_before: str):
        rows = await self.client.rpc(
            "claim_next_article_collection_item",
            {
                "p_worker_id": worker_id,
                "p_stale_before": stale_before,
            },
        )
        return rows[0] if rows else None
