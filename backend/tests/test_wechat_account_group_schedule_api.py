import inspect
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from apis import wechat_account_groups as groups_api
from core.integrations.supabase.auth import get_current_admin_user
from schemas.wechat_account_groups import WeChatAccountGroupScheduleUpdate


class WechatAccountGroupScheduleApiTest(unittest.IsolatedAsyncioTestCase):
    def test_enabled_schedule_requires_time(self):
        with self.assertRaises(ValidationError):
            WeChatAccountGroupScheduleUpdate(enabled=True, collection_pages=1)

    def test_collection_pages_are_bounded(self):
        for pages in (0, 6):
            with self.subTest(pages=pages), self.assertRaises(ValidationError):
                WeChatAccountGroupScheduleUpdate(
                    enabled=True, time="00:30", collection_pages=pages
                )

    def test_update_schedule_requires_admin(self):
        dependency = inspect.signature(
            groups_api.update_wechat_account_group_schedule
        ).parameters["_current_user"].default
        self.assertIs(dependency.dependency, get_current_admin_user)

    @patch.object(
        groups_api.wechat_account_group_repo,
        "get_group_by_id",
        new_callable=AsyncMock,
    )
    @patch.object(
        groups_api.wechat_account_group_repo,
        "update_group_schedule",
        new_callable=AsyncMock,
        create=True,
    )
    @patch.object(
        groups_api.wechat_account_group_repo,
        "get_wechat_account_ids_by_group",
        new_callable=AsyncMock,
    )
    async def test_update_schedule_persists_normalized_values(
        self, get_account_ids, update, get_group
    ):
        get_group.return_value = {"id": 7, "name": "Museums"}
        update.return_value = [{"id": 7, "schedule_enabled": True}]
        get_account_ids.return_value = []
        payload = WeChatAccountGroupScheduleUpdate(
            enabled=True, time="00:30", collection_pages=2
        )

        result = await groups_api.update_wechat_account_group_schedule(
            "7", payload, {"role": "admin"}
        )

        update.assert_awaited_once_with(
            "7",
            schedule_enabled=True,
            schedule_time="00:30:00",
            collection_pages=2,
        )
        self.assertEqual(result["code"], 0)

    @patch.object(
        groups_api.wechat_account_group_repo, "count_groups", new_callable=AsyncMock
    )
    @patch.object(
        groups_api.wechat_account_group_repo, "get_groups", new_callable=AsyncMock
    )
    @patch.object(
        groups_api.wechat_account_group_repo,
        "get_wechat_account_ids_by_group",
        new_callable=AsyncMock,
    )
    @patch.object(
        groups_api.article_collection_repo,
        "get_runs_by_ids",
        new_callable=AsyncMock,
    )
    async def test_group_list_batches_last_run_summaries(
        self, get_runs, get_account_ids, get_groups, count_groups
    ):
        count_groups.return_value = 1
        get_groups.return_value = [
            {"id": 7, "name": "Museums", "last_collection_run_id": "run-1"}
        ]
        get_account_ids.return_value = ["account-1"]
        get_runs.return_value = [
            {
                "id": "run-1",
                "status": "success",
                "articles_count": 3,
                "error": "",
            }
        ]

        result = await groups_api.list_wechat_account_groups(
            _current_user={"id": "user-1"}
        )

        get_runs.assert_awaited_once_with(["run-1"])
        item = result["data"]["list"][0]
        self.assertEqual(item["last_collection_run"]["status"], "success")
        self.assertEqual(item["last_collection_run"]["articles_count"], 3)


if __name__ == "__main__":
    unittest.main()
