from typing import Optional, Dict, Any


class ActivitiesRepository:

    ACTIVITY_TABLE = "activities"

    def __init__(self, client: Any):
        self.client = client

    async def get_activities(
        self,
        article_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        """获取活动列表"""
        filters: Dict[str, Any] = {}
        if article_id is not None:
            filters["article_id"] = article_id

        return await self.client.select(
            self.ACTIVITY_TABLE,
            filters=filters or None,
            limit=limit,
            offset=offset,
            order="created_at.desc",
        )

    async def get_activity_by_id(self, activity_id: str):
        """根据 ID 获取活动"""
        result = await self.client.select(
            self.ACTIVITY_TABLE,
            filters={"id": activity_id},
            limit=1,
        )
        return result[0] if result else None

    async def create_activity(self, activity_data: Dict):
        """创建活动"""
        return await self.client.insert(self.ACTIVITY_TABLE, activity_data)

    async def update_activity(self, activity_id: str, activity_data: Dict):
        """更新活动"""
        return await self.client.update(
            self.ACTIVITY_TABLE, activity_data, filters={"id": activity_id}
        )

    async def delete_activity(self, activity_id: str):
        """删除活动"""
        result = await self.client.delete(
            self.ACTIVITY_TABLE, filters={"id": activity_id}
        )
        return bool(result)

    async def get_activity_article_ids(self):
        """获取已生成活动的文章 ID 列表。"""
        rows = await self.client.select(
            self.ACTIVITY_TABLE,
            columns="article_id",
        )
        return [row["article_id"] for row in rows if row.get("article_id")]
