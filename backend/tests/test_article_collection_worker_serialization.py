import inspect
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
INITIAL_SCHEMA = ROOT / "supabase/migrations/20241120_initial_schema.sql"
SERIAL_CLAIM_MIGRATION = (
    ROOT / "supabase/migrations/20260624_serialize_article_collection_runs.sql"
)


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

    def test_worker_source_declares_global_wechat_session_serial_constraint(self):
        from core.articles import collection_service

        source = inspect.getsource(collection_service)

        self.assertIn("WECHAT_MP_SESSION_SERIAL_REASON", source)
        self.assertIn("shared WeChat MP session is global", source)
        self.assertIn("global_serial=True", source)
        self.assertIn("_execute_collection_run", source)

    def test_article_collection_concurrency_env_is_not_supported(self):
        from core.articles import collection_service

        source = inspect.getsource(collection_service)

        unsupported_env = "ARTICLE_COLLECTION" + "_CONCURRENCY"
        self.assertNotIn(unsupported_env, source)
        self.assertNotIn("WORKER_CONCURRENCY", source)

    def test_uvicorn_workers_are_forced_to_one(self):
        import main

        source = inspect.getsource(main)

        self.assertIn("shared WeChat MP session is global", source)
        self.assertIn("workers = 1", source)

    def test_worker_claims_runs_not_items(self):
        from core.articles import collection_service
        from core.articles.collection_repo import ArticleCollectionRepository

        service_source = inspect.getsource(collection_service._article_collection_worker_loop)
        repo_source = inspect.getsource(ArticleCollectionRepository)

        self.assertIn("claim_next_run", service_source)
        self.assertNotIn("claim_next_item", service_source)
        self.assertIn("claim_next_run", repo_source)

    def test_article_collection_run_claim_is_database_serialized(self):
        for path in (INITIAL_SCHEMA, SERIAL_CLAIM_MIGRATION):
            sql = path.read_text().lower()
            with self.subTest(path=path.name):
                self.assertIn("claim_next_article_collection_run", sql)
                self.assertIn("pg_try_advisory_xact_lock", sql)
                self.assertIn("not exists", sql)
                self.assertIn("status = 'processing'", sql)
                self.assertIn("public.article_collection_runs", sql)


if __name__ == "__main__":
    unittest.main()
