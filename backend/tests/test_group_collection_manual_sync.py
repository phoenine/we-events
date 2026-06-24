from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, patch


class GroupCollectionManualSyncTest(unittest.IsolatedAsyncioTestCase):
    @patch("apis.wechat_account_groups.enqueue_group_collection", new_callable=AsyncMock)
    @patch.object(
        __import__("apis.wechat_account_groups", fromlist=["wechat_account_group_repo"]).wechat_account_group_repo,
        "mark_schedule_attempt",
        new_callable=AsyncMock,
    )
    async def test_manual_group_sync_updates_last_collection_result(
        self, mark_schedule_attempt, enqueue
    ):
        from apis import wechat_account_groups

        enqueue.return_value = {
            "run_id": "run-1",
            "started_account_ids": ["account-1"],
            "skipped_accounts": [],
        }

        result = await wechat_account_groups.sync_wechat_account_group_articles(
            "2", {"start_page": 0, "end_page": 1}, {"id": "user-1"}
        )

        enqueue.assert_awaited_once_with("2", start_page=0, max_page=1)
        payload = mark_schedule_attempt.await_args.args[1]
        self.assertEqual(payload["last_collection_run_id"], "run-1")
        self.assertEqual(payload["last_schedule_error"], "")
        self.assertIn("last_scheduled_at", payload)
        self.assertEqual(result["code"], 0)

    def test_wx_start_does_not_mark_account_as_fetched_before_collection(self):
        from core.integrations.wx import base

        gather = object.__new__(base.WxGather)
        gather.articles = ["stale"]
        gather.cookies = "cookie=value"
        gather.headers = {"Cookie": "cookie=value", "User-Agent": "ua"}
        gather.user_agent = "ua"
        gather.session = None
        gather.hooks = base.WxGatherHooks(
            on_update_wechat_account=lambda *_args: self.fail(
                "Start must not update fetch metadata"
            )
        )

        with patch.object(gather, "ensure_http_context") as ensure_http_context:
            gather.Start("account-1")

        ensure_http_context.assert_called_once_with(force_refresh=True)
        self.assertEqual(gather.articles, [])


if __name__ == "__main__":
    unittest.main()
