from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ActivitiesRepository:
    ACTIVITY_TABLE = "activities"

    def __init__(self, client: Any):
        self.client = client

    async def get_activities(
        self,
        *,
        article_id: str | None = None,
        review_status: str | None = None,
        event_status: str | None = None,
        source_wechat_account_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        filters: dict[str, Any] = {}
        if article_id:
            filters["article_id"] = article_id
        if review_status:
            filters["review_status"] = review_status
        if event_status:
            filters["event_status"] = event_status
        if source_wechat_account_id:
            filters["source_wechat_account_id"] = source_wechat_account_id
        if date_from or date_to:
            start_filter: dict[str, str] = {}
            if date_from:
                start_filter["gte"] = date_from
            if date_to:
                start_filter["lte"] = date_to
            filters["start_at"] = start_filter

        return await self.client.select(
            self.ACTIVITY_TABLE,
            filters=filters or None,
            limit=limit,
            offset=offset,
            order="start_at.desc,created_at.desc",
        )

    async def get_activity_by_id(self, activity_id: str):
        rows = await self.client.select(
            self.ACTIVITY_TABLE,
            filters={"id": activity_id},
            limit=1,
        )
        return rows[0] if rows else None

    async def create_activity(self, activity_data: dict[str, Any]):
        return await self.client.insert(self.ACTIVITY_TABLE, activity_data)

    async def create_activities(self, activities: list[dict[str, Any]]):
        if not activities:
            return []
        rows = []
        for activity in activities:
            rows.append(await self.create_activity(activity))
        return rows

    async def update_activity(self, activity_id: str, activity_data: dict[str, Any]):
        activity_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.client.update(
            self.ACTIVITY_TABLE,
            activity_data,
            filters={"id": activity_id},
        )

    async def delete_activity(self, activity_id: str):
        rows = await self.client.delete(
            self.ACTIVITY_TABLE,
            filters={"id": activity_id},
        )
        return bool(rows)

    async def delete_activities_by_article(self, article_id: str):
        return await self.client.delete(
            self.ACTIVITY_TABLE,
            filters={"article_id": article_id},
        )


class ActivityExtractionRunsRepository:
    RUN_TABLE = "activity_extraction_runs"

    def __init__(self, client: Any):
        self.client = client

    async def create_run(self, run_data: dict[str, Any]):
        return await self.client.insert(self.RUN_TABLE, run_data)

    async def get_run_by_id(self, run_id: str):
        rows = await self.client.select(
            self.RUN_TABLE,
            filters={"id": run_id},
            limit=1,
        )
        return rows[0] if rows else None

    async def update_run(self, run_id: str, run_data: dict[str, Any]):
        run_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.client.update(
            self.RUN_TABLE,
            run_data,
            filters={"id": run_id},
        )
