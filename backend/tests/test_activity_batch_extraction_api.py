import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from apis import activities as activities_api


class ActivityBatchExtractionApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_summary_and_enqueue_return_service_results(self):
        summary_endpoint = getattr(
            activities_api,
            "activity_extraction_summary",
            None,
        )
        enqueue_endpoint = getattr(
            activities_api,
            "extract_pending_activities",
            None,
        )
        self.assertIsNotNone(summary_endpoint)
        self.assertIsNotNone(enqueue_endpoint)

        with patch(
            "apis.activities.get_activity_extraction_summary",
            new=AsyncMock(
                return_value={"pending_count": 8, "processing_count": 3}
            ),
        ):
            response = await summary_endpoint(_current_user={"id": "user-1"})
        self.assertEqual(response["data"]["pending_count"], 8)

        with patch(
            "apis.activities.enqueue_pending_activity_extractions",
            new=AsyncMock(
                return_value={
                    "matched_count": 8,
                    "queued_count": 7,
                    "skipped_count": 1,
                }
            ),
        ):
            response = await enqueue_endpoint(_current_user={"id": "user-1"})
        self.assertEqual(response["data"]["queued_count"], 7)

    async def test_enqueue_maps_empty_pending_set_to_bad_request(self):
        enqueue_endpoint = getattr(
            activities_api,
            "extract_pending_activities",
            None,
        )
        self.assertIsNotNone(enqueue_endpoint)
        with patch(
            "apis.activities.enqueue_pending_activity_extractions",
            new=AsyncMock(side_effect=ValueError("暂无待抽取文章")),
        ):
            with self.assertRaises(HTTPException) as raised:
                await enqueue_endpoint(_current_user={"id": "user-1"})

        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
