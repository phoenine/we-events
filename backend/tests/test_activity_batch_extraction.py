import os
import unittest
from unittest.mock import AsyncMock, patch

from core.activities.repo import ActivityExtractionRunsRepository
from core.activities import service


class ActivityExtractionRunsRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_pending_runs_calls_rpc(self):
        client = AsyncMock()
        client.rpc.return_value = [
            {"matched_count": 4, "queued_count": 3, "skipped_count": 1}
        ]
        repo = ActivityExtractionRunsRepository(client)
        enqueue = getattr(repo, "enqueue_pending_runs", None)
        self.assertIsNotNone(enqueue)

        result = await enqueue(prompt_version="activity_extraction.v2")

        client.rpc.assert_awaited_once_with(
            "enqueue_pending_activity_extractions",
            {"p_prompt_version": "activity_extraction.v2"},
        )
        self.assertEqual(result["queued_count"], 3)


class ActivityBatchExtractionServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_summary_counts_pending_and_processing(self):
        get_summary = getattr(service, "get_activity_extraction_summary", None)
        self.assertIsNotNone(get_summary)
        with patch.object(
            service.article_repo,
            "count_articles_base",
            new=AsyncMock(side_effect=[7, 2]),
        ):
            result = await get_summary()

        self.assertEqual(result, {"pending_count": 7, "processing_count": 2})

    async def test_enqueue_validates_configuration_and_normalizes_counts(self):
        enqueue = getattr(
            service,
            "enqueue_pending_activity_extractions",
            None,
        )
        self.assertIsNotNone(enqueue)
        unavailable_error = getattr(
            service,
            "ActivityExtractionUnavailableError",
            RuntimeError,
        )

        rpc = AsyncMock()
        with (
            patch.dict(os.environ, {"LLM_API_KEY": ""}, clear=False),
            patch.object(service, "WORKER_ENABLED", True),
            patch.object(
                service.activity_run_repo,
                "enqueue_pending_runs",
                new=rpc,
                create=True,
            ),
        ):
            with self.assertRaisesRegex(unavailable_error, "LLM_API_KEY"):
                await enqueue()
        rpc.assert_not_awaited()

        with (
            patch.dict(
                os.environ,
                {"LLM_API_KEY": "configured"},
                clear=False,
            ),
            patch.object(service, "WORKER_ENABLED", True),
            patch.object(
                service.activity_run_repo,
                "enqueue_pending_runs",
                new=AsyncMock(
                    return_value={
                        "matched_count": 5,
                        "queued_count": 4,
                        "skipped_count": 1,
                    }
                ),
                create=True,
            ),
        ):
            result = await enqueue()

        self.assertEqual(
            result,
            {"matched_count": 5, "queued_count": 4, "skipped_count": 1},
        )


if __name__ == "__main__":
    unittest.main()
