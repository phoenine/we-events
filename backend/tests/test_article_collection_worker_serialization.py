import inspect
import unittest
from unittest.mock import patch


class ArticleCollectionWorkerSerializationTest(unittest.TestCase):
    def test_article_collection_starts_single_worker(self):
        from core.articles import collection_service

        created = []

        with (
            patch.object(collection_service, "WORKER_ENABLED", True),
            patch.object(collection_service, "_worker_tasks", []),
            patch.object(collection_service, "_worker_stop_event", None),
            patch.object(collection_service.asyncio, "create_task") as create_task,
        ):
            create_task.side_effect = lambda coro, name=None: created.append(
                (coro, name)
            ) or object()

            try:
                collection_service.asyncio.run(
                    collection_service.start_article_collection_workers()
                )
            finally:
                for coro, _name in created:
                    coro.close()
                collection_service._worker_tasks.clear()
                collection_service._worker_stop_event = None

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][1], "article-collection-worker-1")

    def test_article_collection_concurrency_env_is_not_supported(self):
        from core.articles import collection_service

        source = inspect.getsource(collection_service)

        unsupported_env = "ARTICLE_COLLECTION" + "_CONCURRENCY"
        self.assertNotIn(unsupported_env, source)
        self.assertNotIn("WORKER_CONCURRENCY", source)

    def test_uvicorn_workers_are_forced_to_one(self):
        import main

        source = inspect.getsource(main)

        self.assertIn("Article collection uses a shared WeChat MP session", source)
        self.assertIn("workers = 1", source)


if __name__ == "__main__":
    unittest.main()
