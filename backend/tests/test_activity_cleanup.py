import unittest
from unittest.mock import AsyncMock, patch

from apis import activities as activities_api
from core.activities.repo import ActivitiesRepository
from core.integrations.supabase.auth import get_current_user


class ActivityCleanupRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_delete_activities_by_ids_uses_fixed_id_filter(self):
        client = AsyncMock()
        client.delete.return_value = [
            {"id": "activity-1"},
            {"id": "activity-2"},
        ]
        repo = ActivitiesRepository(client)

        deleted_count = await repo.delete_activities_by_ids(
            ["activity-1", "activity-2"]
        )

        client.delete.assert_awaited_once_with(
            "activities",
            filters={"id": {"in": ["activity-1", "activity-2"]}},
        )
        self.assertEqual(deleted_count, 2)


class ActivityCleanupApiTest(unittest.IsolatedAsyncioTestCase):
    def test_endpoint_uses_signed_in_user_dependency(self):
        route = next(
            route
            for route in activities_api.router.routes
            if route.path == "/activities/ended" and "DELETE" in route.methods
        )

        dependency = route.dependant.dependencies[0].call

        self.assertIs(dependency, get_current_user)

    async def test_delete_ended_activities_returns_deleted_count(self):
        get_activities = AsyncMock(
            return_value=[
                {
                    "id": "activity-ended",
                    "event_status": "ongoing",
                    "start_at": "2000-01-01T00:00:00+08:00",
                    "end_at": None,
                },
                {
                    "id": "activity-upcoming",
                    "event_status": "ended",
                    "start_at": "2099-01-01T00:00:00+08:00",
                    "end_at": None,
                },
            ]
        )
        cleanup = AsyncMock(return_value=1)
        with (
            patch.object(
                activities_api.activity_repo,
                "get_activities",
                new=get_activities,
            ),
            patch.object(
                activities_api.activity_repo,
                "delete_activities_by_ids",
                new=cleanup,
                create=True,
            ),
        ):
            response = await activities_api.delete_ended_activities(
                _current_user={"id": "user-1", "role": "user"},
            )

        cleanup.assert_awaited_once_with(["activity-ended"])
        self.assertEqual(
            response["data"],
            {
                "message": "已删除全部已结束活动",
                "deleted_count": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
