from datetime import datetime
import inspect
import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


class ScheduledGroupCollectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_matching_schedule_is_marked_then_enqueued(self):
        from core.wechat_account_groups.scheduler import run_schedule_tick

        repo = AsyncMock()
        repo.get_enabled_schedules.return_value = [
            {
                "id": 7,
                "schedule_time": "00:30:00",
                "collection_pages": 2,
                "last_scheduled_date": None,
            }
        ]
        enqueue = AsyncMock(return_value={"run_id": "run-1"})
        now = datetime(2026, 6, 22, 0, 30, 15, tzinfo=SHANGHAI)

        await run_schedule_tick(now=now, repo=repo, enqueue=enqueue)

        first_payload = repo.mark_schedule_attempt.await_args_list[0].args[1]
        self.assertEqual(first_payload["last_scheduled_date"], "2026-06-22")
        enqueue.assert_awaited_once_with("7", start_page=0, max_page=2)
        self.assertEqual(repo.mark_schedule_attempt.await_count, 2)
        success_payload = repo.mark_schedule_attempt.await_args_list[1].args[1]
        self.assertEqual(success_payload["last_collection_run_id"], "run-1")
        self.assertEqual(success_payload["last_schedule_error"], "")

    async def test_nonmatching_or_already_attempted_schedule_is_skipped(self):
        from core.wechat_account_groups.scheduler import run_schedule_tick

        repo = AsyncMock()
        repo.get_enabled_schedules.return_value = [
            {"id": 1, "schedule_time": "01:00:00", "collection_pages": 1},
            {
                "id": 2,
                "schedule_time": "00:30:00",
                "collection_pages": 1,
                "last_scheduled_date": "2026-06-22",
            },
        ]
        enqueue = AsyncMock()

        await run_schedule_tick(
            now=datetime(2026, 6, 22, 0, 30, tzinfo=SHANGHAI),
            repo=repo,
            enqueue=enqueue,
        )

        enqueue.assert_not_awaited()
        repo.mark_schedule_attempt.assert_not_awaited()

    async def test_enqueue_error_is_recorded_without_retry(self):
        from core.wechat_account_groups.scheduler import run_schedule_tick

        repo = AsyncMock()
        repo.get_enabled_schedules.return_value = [
            {"id": 7, "schedule_time": "00:30:00", "collection_pages": 1}
        ]
        enqueue = AsyncMock(side_effect=RuntimeError("queue unavailable"))

        await run_schedule_tick(
            now=datetime(2026, 6, 22, 0, 30, tzinfo=SHANGHAI),
            repo=repo,
            enqueue=enqueue,
        )

        self.assertEqual(enqueue.await_count, 1)
        error_payload = repo.mark_schedule_attempt.await_args_list[-1].args[1]
        self.assertIn("queue unavailable", error_payload["last_schedule_error"])

    async def test_scheduler_start_and_stop_are_idempotent(self):
        from core.wechat_account_groups import scheduler

        with patch.object(scheduler, "run_schedule_tick", new_callable=AsyncMock):
            await scheduler.start_group_collection_scheduler()
            first_task = scheduler._scheduler_task
            await scheduler.start_group_collection_scheduler()

            self.assertIs(scheduler._scheduler_task, first_task)

            await scheduler.stop_group_collection_scheduler()
            await scheduler.stop_group_collection_scheduler()
            self.assertIsNone(scheduler._scheduler_task)

    def test_lifespan_starts_and_stops_group_scheduler(self):
        import web

        source = inspect.getsource(web.lifespan)
        self.assertIn("start_group_collection_scheduler", source)
        self.assertIn("stop_group_collection_scheduler", source)
        self.assertLess(
            source.index("stop_group_collection_scheduler"),
            source.index("stop_article_collection_workers"),
        )


if __name__ == "__main__":
    unittest.main()
