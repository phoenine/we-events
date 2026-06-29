import inspect
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[2]
INITIAL_SCHEMA = ROOT / "supabase/migrations/20241120_initial_schema.sql"
ORPHAN_REPAIR_MIGRATION = (
    ROOT / "supabase/migrations/20260629_repair_article_collection_orphans.sql"
)
COMPOSE_FILE = ROOT / "docker-compose.yaml"


class ArticleCollectionWorkerSerializationTest(unittest.TestCase):
    def test_worker_without_local_wechat_session_does_not_claim_run(self):
        from core.articles import collection_service

        async def scenario():
            stop_event = collection_service.asyncio.Event()
            claim_next_run = AsyncMock(return_value=None)

            async def stop_after_wait(awaitable, *, timeout):
                stop_event.set()
                return await awaitable

            diagnostics = collection_service.WechatSessionDiagnostics(
                persisted_session_exists=False,
                persisted_cookie_count=0,
                cookie_header_present=False,
                session_cookie_count=0,
                persisted_token_exists=False,
                has_user_agent=False,
            )
            with (
                patch.object(
                    collection_service,
                    "_wechat_session_diagnostics",
                    return_value=diagnostics,
                ),
                patch.object(
                    collection_service.article_collection_repo,
                    "claim_next_run",
                    claim_next_run,
                ),
                patch.object(
                    collection_service.asyncio,
                    "wait_for",
                    side_effect=stop_after_wait,
                ),
            ):
                await collection_service._article_collection_worker_loop(
                    "worker-without-session",
                    stop_event,
                )

            claim_next_run.assert_not_awaited()

        collection_service.asyncio.run(scenario())

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
        sql = INITIAL_SCHEMA.read_text().lower()

        self.assertIn("claim_next_article_collection_run", sql)
        self.assertIn("pg_try_advisory_xact_lock", sql)
        self.assertIn("not exists", sql)
        self.assertIn("status = 'processing'", sql)
        self.assertIn("public.article_collection_runs", sql)
        self.assertIn("item.status in ('queued', 'processing')", sql)
        self.assertIn(
            "run.status in ('success', 'partial_success', 'failed', 'canceled')",
            sql,
        )

    def test_terminal_runs_cleanup_active_child_items(self):
        sql = ORPHAN_REPAIR_MIGRATION.read_text().lower()

        self.assertIn(
            "create or replace function public.claim_next_article_collection_run",
            sql,
        )
        self.assertIn("from public.article_collection_runs as run", sql)
        self.assertIn("item.status in ('queued', 'processing')", sql)
        self.assertIn(
            "run.status in ('success', 'partial_success', 'failed', 'canceled')",
            sql,
        )

    def test_compose_forwards_collection_ownership_switches(self):
        compose = COMPOSE_FILE.read_text()

        self.assertIn("ARTICLE_COLLECTION_WORKER_ENABLED:", compose)
        self.assertIn("GROUP_COLLECTION_SCHEDULER_ENABLED:", compose)


if __name__ == "__main__":
    unittest.main()
