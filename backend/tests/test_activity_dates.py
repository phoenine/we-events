from datetime import date, datetime
import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from apis import activities as activities_api
from core.activities.agent import _build_prompt
from core.activities.extraction_input import format_article_publish_date
from core.activities.extraction_output import (
    ActivityExtractionOutput,
    ExtractedActivity,
    compute_event_status,
)
from core.activities.service import _activity_row
from schemas.activities import ActivityCreate, ActivityUpdate


SHANGHAI = ZoneInfo("Asia/Shanghai")


class ActivityRelativeDateTest(unittest.TestCase):
    def test_publish_timestamp_is_exposed_as_shanghai_date(self):
        publish_time = int(datetime(2026, 6, 15, 0, 30, tzinfo=SHANGHAI).timestamp())

        self.assertEqual(format_article_publish_date(publish_time), "2026-06-15")

    def test_relative_start_uses_article_publish_date(self):
        publish_time = int(datetime(2026, 6, 15, 9, 30, tzinfo=SHANGHAI).timestamp())
        activity = ExtractedActivity(
            title="暑期活动",
            event_time_text="即日起至2026年7月19日",
            start_at="2026-07-19T00:00:00+08:00",
            end_at="2026-07-19T23:59:59+08:00",
        )
        output = ActivityExtractionOutput(
            is_activity_article=True,
            confidence=0.9,
            activities=[activity],
        )

        row = _activity_row(
            article={
                "id": "article-1",
                "url": "https://example.com/article-1",
                "publish_time": publish_time,
                "wechat_account": {"id": "account-1"},
            },
            run_id="run-1",
            output=output,
            activity=activity,
        )

        self.assertEqual(row["event_time_text"], "2026年6月15日至2026年7月19日")
        self.assertEqual(row["start_at"], "2026-06-15T00:00:00+08:00")
        self.assertEqual(row["end_at"], "2026-07-19T23:59:59+08:00")

    def test_prompt_resolves_relative_dates_against_publish_date(self):
        prompt = _build_prompt(
            {
                "article": {
                    "title": "暑期活动",
                    "publish_date": "2026-06-15",
                },
                "content": {"text": "即日起至2026年7月19日"},
                "images": [],
                "options": {"timezone": "Asia/Shanghai"},
            }
        )

        self.assertIn("article.publish_date", prompt)
        self.assertIn("event_time_text 也必须改写为具体日期", prompt)


class ActivityStatusTest(unittest.TestCase):
    def test_status_cases(self):
        today = date(2026, 6, 15)
        cases = [
            ("2026-06-15T00:00:00+08:00", None, "ongoing"),
            ("2026-06-16T00:00:00+08:00", None, "upcoming"),
            ("2026-06-14T00:00:00+08:00", None, "ended"),
            ("2026-06-01T00:00:00+08:00", "2026-06-15T23:59:59+08:00", "ended"),
            ("2026-06-01T00:00:00+08:00", "2026-06-14T23:59:59+08:00", "ended"),
            (None, "2026-06-16T23:59:59+08:00", "ongoing"),
            (None, None, "unknown"),
        ]

        for start_at, end_at, expected in cases:
            with self.subTest(start_at=start_at, end_at=end_at):
                self.assertEqual(
                    compute_event_status(start_at, end_at, today=today),
                    expected,
                )


class ActivityStatusApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_list_recomputes_stale_statuses(self):
        rows = [
            {
                "id": "activity-1",
                "start_at": "2099-06-16T00:00:00+08:00",
                "end_at": None,
                "event_status": "ongoing",
            }
        ]
        with patch.object(
            activities_api.activity_repo,
            "get_activities",
            new=AsyncMock(return_value=rows),
        ):
            response = await activities_api.list_activities(
                _current_user={"id": "user-1"},
            )

        self.assertEqual(response["data"][0]["event_status"], "upcoming")

    async def test_list_filters_after_recomputing_stale_statuses(self):
        stale_row = {
            "id": "activity-1",
            "start_at": "2026-06-14T00:00:00+08:00",
            "end_at": None,
            "event_status": "ongoing",
        }

        async def get_activities(**kwargs):
            return [] if kwargs["event_status"] else [stale_row]

        with patch.object(
            activities_api.activity_repo,
            "get_activities",
            new=AsyncMock(side_effect=get_activities),
        ):
            response = await activities_api.list_activities(
                article_id=None,
                review_status=None,
                event_status="ended",
                source_wechat_account_id=None,
                date_from=None,
                date_to=None,
                limit=20,
                offset=0,
                _current_user={"id": "user-1"},
            )

        self.assertEqual([item["id"] for item in response["data"]], ["activity-1"])

    async def test_create_ignores_client_status_and_computes_from_dates(self):
        payload = ActivityCreate(
            article_id="article-1",
            title="未来活动",
            start_at="2099-06-16T00:00:00+08:00",
            event_status="ended",
        )
        create = AsyncMock(side_effect=lambda data: data)
        with (
            patch.object(
                activities_api.article_repo,
                "get_articles_by_id",
                new=AsyncMock(return_value=[{"id": "article-1"}]),
            ),
            patch.object(
                activities_api.activity_repo,
                "create_activity",
                new=create,
            ),
        ):
            response = await activities_api.create_activity(
                payload,
                _current_user={"id": "user-1"},
            )

        self.assertEqual(response["data"]["event_status"], "upcoming")

    async def test_patch_ignores_client_status_and_recomputes_from_existing_dates(self):
        payload = ActivityUpdate(event_status="ended")
        update = AsyncMock(side_effect=lambda _activity_id, data: [data])
        with (
            patch.object(
                activities_api.activity_repo,
                "get_activity_by_id",
                new=AsyncMock(
                    return_value={
                        "id": "activity-1",
                        "start_at": "2099-06-16T00:00:00+08:00",
                        "end_at": None,
                    }
                ),
            ),
            patch.object(
                activities_api.activity_repo,
                "update_activity",
                new=update,
            ),
        ):
            response = await activities_api.patch_activity(
                "activity-1",
                payload,
                _current_user={"id": "user-1"},
            )

        self.assertEqual(response["data"]["event_status"], "upcoming")


if __name__ == "__main__":
    unittest.main()
