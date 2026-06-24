import unittest
from unittest.mock import AsyncMock, patch


class ArticleCollectionRunExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_execute_collection_item_does_not_refresh_run_summary(self):
        from core.articles import collection_service

        item = {
            "id": "item-1",
            "run_id": "run-1",
            "wechat_account_id": "account-1",
            "start_page": 0,
            "max_page": 1,
            "attempt_count": 1,
            "max_attempts": 2,
        }
        update_item = AsyncMock()
        refresh_summary = AsyncMock()
        with (
            patch.object(
                collection_service.wechat_account_repo,
                "get_wechat_account_by_id",
                new=AsyncMock(return_value={"id": "account-1", "name": "Account"}),
            ),
            patch.object(
                collection_service,
                "_collect_account_sync",
                return_value={"count": 2},
            ),
            patch.object(
                collection_service,
                "_update_account_fetch_metadata",
                new=AsyncMock(),
            ),
            patch.object(
                collection_service.article_collection_repo,
                "update_item",
                new=update_item,
            ),
            patch.object(
                collection_service,
                "_refresh_run_summary",
                new=refresh_summary,
            ),
        ):
            await collection_service._execute_collection_item(item)

        success_updates = [
            call.args[1]
            for call in update_item.await_args_list
            if call.args[1].get("status") == "success"
        ]
        self.assertEqual(success_updates[0]["articles_count"], 2)
        refresh_summary.assert_not_awaited()

    async def test_execute_collection_run_processes_items_in_created_order(self):
        from core.articles import collection_service

        calls: list[str] = []
        items = [
            {
                "id": "item-1",
                "run_id": "run-1",
                "wechat_account_id": "account-1",
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 1,
            },
            {
                "id": "item-2",
                "run_id": "run-1",
                "wechat_account_id": "account-2",
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 1,
            },
        ]

        async def execute_item(item):
            calls.append(item["id"])

        with (
            patch.object(
                collection_service.article_collection_repo,
                "get_items_by_run",
                new=AsyncMock(return_value=items),
            ),
            patch.object(
                collection_service.article_collection_repo,
                "update_item",
                new=AsyncMock(),
            ),
            patch.object(
                collection_service,
                "_execute_collection_item",
                new=AsyncMock(side_effect=execute_item),
            ),
            patch.object(
                collection_service,
                "_refresh_run_summary",
                new=AsyncMock(return_value={"status": "success"}),
            ),
        ):
            await collection_service._execute_collection_run(
                {"id": "run-1"}, worker_id="worker-1"
            )

        self.assertEqual(calls, ["item-1", "item-2"])

    async def test_session_reuse_error_does_not_stop_remaining_items(self):
        from core.articles import collection_service

        calls: list[str] = []
        items = [
            {
                "id": "item-1",
                "run_id": "run-1",
                "wechat_account_id": "account-1",
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 1,
            },
            {
                "id": "item-2",
                "run_id": "run-1",
                "wechat_account_id": "account-2",
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 1,
            },
        ]
        diagnostics = collection_service.WechatSessionDiagnostics(
            persisted_session_exists=True,
            persisted_cookie_count=2,
            cookie_header_present=False,
            session_cookie_count=0,
            persisted_token_exists=True,
            has_user_agent=True,
        )

        async def execute_item(item):
            calls.append(item["id"])
            if item["id"] == "item-1":
                raise collection_service.WechatCollectionError(
                    "请先扫码登录公众号平台",
                    category="session_reuse_error",
                    diagnostics=diagnostics,
                )

        update_item = AsyncMock()
        with (
            patch.object(
                collection_service.article_collection_repo,
                "get_items_by_run",
                new=AsyncMock(return_value=items),
            ),
            patch.object(
                collection_service.article_collection_repo,
                "update_item",
                new=update_item,
            ),
            patch.object(
                collection_service,
                "_execute_collection_item",
                new=AsyncMock(side_effect=execute_item),
            ),
            patch.object(
                collection_service,
                "_refresh_run_summary",
                new=AsyncMock(return_value={"status": "partial_success"}),
            ),
        ):
            await collection_service._execute_collection_run(
                {"id": "run-1"}, worker_id="worker-1"
            )

        self.assertEqual(calls, ["item-1", "item-2"])
        failed_payloads = [
            call.args[1]
            for call in update_item.await_args_list
            if call.args[1].get("status") == "failed"
        ]
        self.assertIn("微信登录态复用异常", failed_payloads[0]["error"])

    async def test_invalid_session_stops_remaining_items(self):
        from core.articles import collection_service

        calls: list[str] = []
        items = [
            {
                "id": "item-1",
                "run_id": "run-1",
                "wechat_account_id": "account-1",
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 1,
            },
            {
                "id": "item-2",
                "run_id": "run-1",
                "wechat_account_id": "account-2",
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 1,
            },
        ]

        async def execute_item(item):
            calls.append(item["id"])
            raise collection_service.WechatCollectionError(
                "错误原因:invalid session:代码:200003",
                category="invalid_session",
            )

        update_item = AsyncMock()
        with (
            patch.object(
                collection_service.article_collection_repo,
                "get_items_by_run",
                new=AsyncMock(return_value=items),
            ),
            patch.object(
                collection_service.article_collection_repo,
                "update_item",
                new=update_item,
            ),
            patch.object(
                collection_service,
                "_execute_collection_item",
                new=AsyncMock(side_effect=execute_item),
            ),
            patch.object(
                collection_service,
                "_refresh_run_summary",
                new=AsyncMock(return_value={"status": "failed"}),
            ),
        ):
            await collection_service._execute_collection_run(
                {"id": "run-1"}, worker_id="worker-1"
            )

        self.assertEqual(calls, ["item-1"])
        failed_payloads = [
            call.args[1]
            for call in update_item.await_args_list
            if call.args[1].get("status") == "failed"
        ]
        self.assertEqual(len(failed_payloads), 2)
        self.assertIn("微信登录态已失效", failed_payloads[1]["error"])


if __name__ == "__main__":
    unittest.main()
