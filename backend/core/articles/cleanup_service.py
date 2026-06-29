from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from core.articles import article_repo
from core.articles.storage_cleanup import extract_storage_paths_from_content
from core.common.log import logger
from core.integrations.supabase.storage import supabase_storage_articles


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExpiredArticleCleanupService:
    def __init__(self, *, repo=article_repo, storage=supabase_storage_articles):
        self.repo = repo
        self.storage = storage
        self._start_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._status = self._idle_status()

    @staticmethod
    def _idle_status() -> dict[str, Any]:
        return {
            "run_id": "",
            "status": "idle",
            "already_running": False,
            "matched_count": 0,
            "deleted_count": 0,
            "storage_deleted_count": 0,
            "storage_failed_count": 0,
            "started_at": None,
            "finished_at": None,
            "error": "",
        }

    def status(self) -> dict[str, Any]:
        return dict(self._status)

    async def start(self, *, days: int = 7) -> dict[str, Any]:
        async with self._start_lock:
            if self._task is not None and not self._task.done():
                return {**self.status(), "already_running": True}

            self._status = {
                **self._idle_status(),
                "run_id": str(uuid.uuid4()),
                "status": "processing",
                "started_at": _now(),
            }
            self._task = asyncio.create_task(
                self._run(days=days),
                name=f"expired-article-cleanup-{self._status['run_id']}",
            )
            return self.status()

    async def _run(self, *, days: int) -> None:
        try:
            cutoff_ts = int(
                (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
            )
            articles = await self.repo.get_articles_base(
                filters={"publish_time": {"lt": cutoff_ts}},
                columns="id,content",
            )
            article_ids = [
                str(article["id"])
                for article in articles
                if article.get("id")
            ]
            self._status["matched_count"] = len(article_ids)

            mappings = await self.repo.get_article_images_by_articles(article_ids)
            mapped_paths: dict[str, set[str]] = {}
            for mapping in mappings:
                article_id = str(mapping.get("article_id") or "")
                object_path = str(mapping.get("object_path") or "").strip()
                if article_id and object_path:
                    mapped_paths.setdefault(article_id, set()).add(object_path)

            storage_paths: set[str] = set()
            for article in articles:
                article_id = str(article.get("id") or "")
                article_paths = mapped_paths.get(article_id)
                if article_paths:
                    storage_paths.update(article_paths)
                    continue
                storage_paths.update(
                    extract_storage_paths_from_content(
                        str(article.get("content") or "")
                    )
                )

            storage_result = await self.storage.delete_objects(
                sorted(storage_paths),
                concurrency=8,
            )
            self._status["storage_deleted_count"] = int(
                storage_result.get("deleted_count") or 0
            )
            self._status["storage_failed_count"] = int(
                storage_result.get("failed_count") or 0
            )

            deleted = await self.repo.delete_articles_by_ids(article_ids)
            self._status["deleted_count"] = len(deleted)
            self._status["status"] = "success"
        except Exception as exc:
            self._status["status"] = "failed"
            self._status["error"] = (
                f"{type(exc).__name__}: {exc}"
                if str(exc)
                else type(exc).__name__
            )
            logger.exception(
                f"[expired-article-cleanup] failed "
                f"run_id={self._status.get('run_id')}: {self._status['error']}"
            )
        finally:
            self._status["finished_at"] = _now()


expired_article_cleanup_service = ExpiredArticleCleanupService()
