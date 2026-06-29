import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from core.articles.cleanup_service import ExpiredArticleCleanupService
from core.articles.repo import ArticleRepository
from core.integrations.supabase.storage import SupabaseStorage


class _FakeDeleteResponse:
    status_code = 200
    text = ""


class _TrackingAsyncClient:
    def __init__(self, *args, **kwargs):
        self.active = 0
        self.max_active = 0
        self.paths: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def delete(self, url, headers):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.paths.append(url.rsplit("/", 1)[-1])
        await asyncio.sleep(0)
        self.active -= 1
        return _FakeDeleteResponse()


class SupabaseStorageBatchDeleteTest(unittest.IsolatedAsyncioTestCase):
    async def test_delete_objects_reuses_client_and_bounds_concurrency(self):
        client = _TrackingAsyncClient()
        storage = SupabaseStorage("articles")

        with patch(
            "core.integrations.supabase.storage.httpx.AsyncClient",
            return_value=client,
        ) as client_factory:
            result = await storage.delete_objects(
                ["one.jpg", "two.jpg", "three.jpg"],
                concurrency=2,
            )

        self.assertEqual(
            result,
            {"deleted_count": 3, "failed_count": 0},
        )
        self.assertEqual(client_factory.call_count, 1)
        self.assertLessEqual(client.max_active, 2)
        self.assertCountEqual(
            client.paths,
            ["one.jpg", "two.jpg", "three.jpg"],
        )


class ArticleRepositoryCleanupBatchTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_article_images_by_articles_reads_in_chunks(self):
        client = AsyncMock()
        client.select = AsyncMock(
            side_effect=[
                [{"id": "image-1"}],
                [{"id": "image-2"}],
                [{"id": "image-3"}],
            ]
        )
        repo = ArticleRepository(client)
        article_ids = [f"article-{index}" for index in range(205)]

        rows = await repo.get_article_images_by_articles(article_ids)

        self.assertEqual(
            rows,
            [{"id": "image-1"}, {"id": "image-2"}, {"id": "image-3"}],
        )
        self.assertEqual(client.select.await_count, 3)
        client.select.assert_any_await(
            "article_images",
            filters={"article_id": {"in": article_ids[:100]}},
        )

    async def test_delete_articles_by_ids_deletes_in_chunks(self):
        client = AsyncMock()
        client.delete = AsyncMock(
            side_effect=[
                [{"id": "article-1"}],
                [{"id": "article-2"}],
                [{"id": "article-3"}],
            ]
        )
        repo = ArticleRepository(client)
        article_ids = [f"article-{index}" for index in range(205)]

        rows = await repo.delete_articles_by_ids(article_ids)

        self.assertEqual(
            rows,
            [{"id": "article-1"}, {"id": "article-2"}, {"id": "article-3"}],
        )
        self.assertEqual(client.delete.await_count, 3)
        client.delete.assert_any_await(
            "articles",
            {"id": {"in": article_ids[:100]}},
        )


class ExpiredArticleCleanupServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_reuses_running_task(self):
        release = asyncio.Event()
        repo = AsyncMock()

        async def blocked_articles(*args, **kwargs):
            await release.wait()
            return []

        repo.get_articles_base = AsyncMock(side_effect=blocked_articles)
        repo.get_article_images_by_articles = AsyncMock(return_value=[])
        repo.delete_articles_by_ids = AsyncMock(return_value=[])
        storage = AsyncMock()
        storage.delete_objects = AsyncMock(
            return_value={"deleted_count": 0, "failed_count": 0}
        )
        service = ExpiredArticleCleanupService(repo=repo, storage=storage)

        first = await service.start()
        await asyncio.sleep(0)
        second = await service.start()

        self.assertEqual(first["run_id"], second["run_id"])
        self.assertFalse(first["already_running"])
        self.assertTrue(second["already_running"])
        self.assertEqual(repo.get_articles_base.await_count, 1)

        release.set()
        await service._task

    async def test_cleanup_batches_mappings_and_uses_html_fallback(self):
        repo = AsyncMock()
        repo.get_articles_base = AsyncMock(
            return_value=[
                {
                    "id": "article-1",
                    "content": '<img src="articles/article-1/fallback.jpg">',
                },
                {
                    "id": "article-2",
                    "content": '<img src="articles/article-2/fallback.jpg">',
                },
            ]
        )
        repo.get_article_images_by_articles = AsyncMock(
            return_value=[
                {
                    "article_id": "article-1",
                    "object_path": "articles/article-1/mapped.jpg",
                }
            ]
        )
        repo.delete_articles_by_ids = AsyncMock(
            return_value=[{"id": "article-1"}, {"id": "article-2"}]
        )
        storage = AsyncMock()
        storage.delete_objects = AsyncMock(
            return_value={"deleted_count": 2, "failed_count": 0}
        )
        service = ExpiredArticleCleanupService(repo=repo, storage=storage)

        await service.start(days=7)
        await service._task
        status = service.status()

        repo.get_article_images_by_articles.assert_awaited_once_with(
            ["article-1", "article-2"]
        )
        storage.delete_objects.assert_awaited_once()
        paths = storage.delete_objects.await_args.args[0]
        self.assertCountEqual(
            paths,
            [
                "articles/article-1/mapped.jpg",
                "articles/article-2/fallback.jpg",
            ],
        )
        repo.delete_articles_by_ids.assert_awaited_once_with(
            ["article-1", "article-2"]
        )
        self.assertEqual(status["status"], "success")
        self.assertEqual(status["matched_count"], 2)
        self.assertEqual(status["deleted_count"], 2)
        self.assertEqual(status["storage_deleted_count"], 2)

    async def test_cleanup_records_failure_status(self):
        repo = AsyncMock()
        repo.get_articles_base = AsyncMock(side_effect=RuntimeError("database down"))
        storage = AsyncMock()
        service = ExpiredArticleCleanupService(repo=repo, storage=storage)

        await service.start()
        await service._task
        status = service.status()

        self.assertEqual(status["status"], "failed")
        self.assertIn("database down", status["error"])
        self.assertIsNotNone(status["finished_at"])


if __name__ == "__main__":
    unittest.main()
