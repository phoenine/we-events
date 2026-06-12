from __future__ import annotations

import asyncio
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from core.articles import article_collection_repo
from core.common.log import logger
from core.common.runtime_settings import runtime_settings
from core.wechat_accounts import wechat_account_repo
from core.wechat_account_groups import wechat_account_group_repo
from core.wechat_accounts.collector import collect_wechat_account_articles
from jobs.article import UpdateArticle, Update_Over


STALE_PROCESSING_MINUTES = int(os.getenv("ARTICLE_COLLECTION_STALE_MINUTES", "45"))
WORKER_ENABLED = os.getenv("ARTICLE_COLLECTION_WORKER_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
}
WORKER_CONCURRENCY = max(1, int(os.getenv("ARTICLE_COLLECTION_CONCURRENCY", "1")))
WORKER_POLL_INTERVAL_SECONDS = max(
    1.0,
    float(os.getenv("ARTICLE_COLLECTION_POLL_INTERVAL_SECONDS", "3")),
)

_worker_tasks: list[asyncio.Task[None]] = []
_worker_stop_event: asyncio.Event | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _last_sync_epoch(account: dict[str, Any]) -> int:
    value = account.get("last_fetch") or account.get("sync_time") or account.get("update_time")
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(float(str(value)))
    except Exception:
        pass
    dt = _parse_datetime(value)
    return int(dt.timestamp()) if dt else 0


def _is_stale_processing_item(item: dict[str, Any]) -> bool:
    if item.get("status") != "processing":
        return False
    started_at = _parse_datetime(item.get("locked_at") or item.get("started_at") or item.get("created_at"))
    if not started_at:
        return False
    return datetime.now(timezone.utc) - started_at > timedelta(
        minutes=STALE_PROCESSING_MINUTES
    )


def _is_account_disabled(account: dict[str, Any]) -> bool:
    return int(account.get("status") or 0) == 0


async def _is_account_in_cooldown(account: dict[str, Any]) -> tuple[bool, int, int]:
    sync_interval = await runtime_settings.get_int("sync_interval", 60)
    time_span = int(datetime.now(timezone.utc).timestamp()) - _last_sync_epoch(account)
    return time_span < sync_interval, time_span, sync_interval


def _max_publish_time_iso(articles: list[dict[str, Any]]) -> str | None:
    timestamps: list[int] = []
    for article in articles:
        try:
            value = int(float(article.get("publish_time") or 0))
        except Exception:
            continue
        if value > 10_000_000_000:
            value = value // 1000
        if value > 0:
            timestamps.append(value)
    if not timestamps:
        return None
    return datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat()


async def _mark_run_empty(run_id: str, *, skipped_count: int = 0, message: str = "") -> None:
    await article_collection_repo.update_run(
        run_id,
        {
            "status": "success",
            "total_items": 0,
            "success_items": 0,
            "failed_items": 0,
            "skipped_items": skipped_count,
            "articles_count": 0,
            "error": message,
            "finished_at": _now(),
        },
    )


async def _mark_item_stale_failed(item: dict[str, Any]) -> None:
    item_id = str(item.get("id") or "")
    run_id = str(item.get("run_id") or "")
    if not item_id:
        return
    await article_collection_repo.update_item(
        item_id,
        {
            "status": "failed",
            "error": "文章采集任务超时未完成，已标记为失败",
            "finished_at": _now(),
            "locked_at": None,
            "locked_by": None,
        },
    )
    if run_id:
        await _refresh_run_summary(run_id)


async def _refresh_run_summary(run_id: str) -> dict[str, Any]:
    items = await article_collection_repo.get_items_by_run(run_id)
    total = len(items)
    success = sum(1 for item in items if item.get("status") == "success")
    failed = sum(1 for item in items if item.get("status") == "failed")
    skipped = sum(1 for item in items if item.get("status") == "skipped")
    active = any(item.get("status") in {"queued", "processing"} for item in items)
    articles_count = sum(int(item.get("articles_count") or 0) for item in items)

    if active:
        status = "processing"
        finished_at = None
    elif failed and success:
        status = "partial_success"
        finished_at = _now()
    elif failed and not success:
        status = "failed"
        finished_at = _now()
    else:
        status = "success"
        finished_at = _now()

    error = ""
    if status == "failed":
        first_error = next((str(item.get("error") or "") for item in items if item.get("error")), "")
        error = first_error or "文章采集失败"

    data: dict[str, Any] = {
        "status": status,
        "total_items": total,
        "success_items": success,
        "failed_items": failed,
        "skipped_items": skipped,
        "articles_count": articles_count,
        "error": error,
    }
    if finished_at:
        data["finished_at"] = finished_at
    await article_collection_repo.update_run(run_id, data)
    run = await article_collection_repo.get_run_by_id(run_id)
    return run or data


async def get_article_collection_run(run_id: str) -> dict[str, Any] | None:
    run = await article_collection_repo.get_run_by_id(run_id)
    if not run:
        return None
    items = await article_collection_repo.get_items_by_run(run_id)
    return {**run, "items": items}


async def enqueue_account_collection(
    wechat_account_id: str,
    *,
    start_page: int = 0,
    max_page: int = 1,
) -> dict[str, Any]:
    account = await wechat_account_repo.get_wechat_account_by_id(wechat_account_id)
    if not account:
        raise ValueError("请选择一个公众号")
    if _is_account_disabled(account):
        raise ValueError("公众号已停用，无法采集")

    active_item = await article_collection_repo.get_latest_active_item_by_account(
        wechat_account_id
    )
    if active_item:
        if _is_stale_processing_item(active_item):
            await _mark_item_stale_failed(active_item)
        else:
            return {
                "run_id": active_item.get("run_id"),
                "item_id": active_item.get("id"),
                "status": active_item.get("status") or "queued",
                "already_running": True,
                "wechat_account_id": wechat_account_id,
            }

    active_item = await article_collection_repo.get_latest_active_item_by_account(
        wechat_account_id
    )
    if active_item:
        return {
            "run_id": active_item.get("run_id"),
            "item_id": active_item.get("id"),
            "status": active_item.get("status") or "queued",
            "already_running": True,
            "wechat_account_id": wechat_account_id,
        }

    in_cooldown, time_span, sync_interval = await _is_account_in_cooldown(account)
    if in_cooldown:
        return {
            "run_id": None,
            "status": "skipped",
            "already_running": False,
            "wechat_account_id": wechat_account_id,
            "skipped_accounts": [
                {
                    "id": wechat_account_id,
                    "reason": "cooldown",
                    "time_span": time_span,
                    "sync_interval": sync_interval,
                }
            ],
        }

    run = await article_collection_repo.create_run(
        {
            "scope": "single_account",
            "status": "queued",
            "start_page": start_page,
            "max_page": max_page,
            "total_items": 1,
        }
    )
    run_id = str(run.get("id") or "")
    if not run_id:
        raise RuntimeError("创建文章采集任务失败")

    try:
        item = await article_collection_repo.create_item(
            {
                "run_id": run_id,
                "wechat_account_id": wechat_account_id,
                "account_snapshot": account,
                "start_page": start_page,
                "max_page": max_page,
            }
        )
    except Exception:
        active_item = await article_collection_repo.get_latest_active_item_by_account(
            wechat_account_id
        )
        if active_item:
            await _mark_run_empty(run_id, skipped_count=1, message="公众号已有采集任务在队列中")
            return {
                "run_id": active_item.get("run_id"),
                "item_id": active_item.get("id"),
                "status": active_item.get("status") or "queued",
                "already_running": True,
                "wechat_account_id": wechat_account_id,
            }
        raise

    return {
        "run_id": run_id,
        "item_id": item.get("id"),
        "status": "queued",
        "already_running": False,
        "wechat_account_id": wechat_account_id,
    }


async def enqueue_group_collection(
    group_id: str,
    *,
    start_page: int = 0,
    max_page: int = 1,
) -> dict[str, Any]:
    group = await wechat_account_group_repo.get_group_by_id(group_id)
    if not group:
        raise ValueError("公众号分组不存在")

    account_ids = await wechat_account_group_repo.get_wechat_account_ids_by_group(group_id)
    if not account_ids:
        return {
            "run_id": None,
            "group_id": group_id,
            "account_count": 0,
            "started_account_ids": [],
            "skipped_accounts": [],
            "status": "skipped",
        }

    accounts = await wechat_account_repo.get_wechat_accounts_by_ids(account_ids)
    runnable: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for account in accounts:
        account_id = str(account.get("id") or "")
        if not account_id:
            continue
        if _is_account_disabled(account):
            skipped.append({"id": account_id, "reason": "disabled"})
            continue
        active_item = await article_collection_repo.get_latest_active_item_by_account(
            account_id
        )
        if active_item:
            if _is_stale_processing_item(active_item):
                await _mark_item_stale_failed(active_item)
            else:
                skipped.append(
                    {
                        "id": account_id,
                        "reason": "already_running",
                        "run_id": active_item.get("run_id"),
                        "item_id": active_item.get("id"),
                        "status": active_item.get("status"),
                    }
                )
                continue
        in_cooldown, time_span, sync_interval = await _is_account_in_cooldown(account)
        if in_cooldown:
            skipped.append(
                {
                    "id": account_id,
                    "reason": "cooldown",
                    "time_span": time_span,
                    "sync_interval": sync_interval,
                }
            )
            continue
        runnable.append(account)

    run = await article_collection_repo.create_run(
        {
            "scope": "group",
            "group_id": int(str(group_id)),
            "status": "queued",
            "start_page": start_page,
            "max_page": max_page,
            "total_items": len(runnable),
            "skipped_items": len(skipped),
        }
    )
    run_id = str(run.get("id") or "")
    if not run_id:
        raise RuntimeError("创建分组采集任务失败")

    created: list[dict[str, Any]] = []
    for account in runnable:
        account_id = str(account.get("id") or "")
        try:
            created.append(
                await article_collection_repo.create_item(
                    {
                        "run_id": run_id,
                        "wechat_account_id": account_id,
                        "account_snapshot": account,
                        "start_page": start_page,
                        "max_page": max_page,
                    }
                )
            )
        except Exception:
            skipped.append({"id": account_id, "reason": "already_running"})

    await article_collection_repo.update_run(
        run_id,
        {
            "total_items": len(created),
            "skipped_items": len(skipped),
            "status": "queued" if created else "success",
            **({"finished_at": _now()} if not created else {}),
        },
    )

    return {
        "run_id": run_id,
        "group_id": group_id,
        "account_count": len(accounts),
        "started_account_ids": [
            str(item.get("wechat_account_id")) for item in created if item.get("wechat_account_id")
        ],
        "skipped_accounts": skipped,
        "start_page": start_page,
        "end_page": max_page,
        "status": "queued" if created else "success",
    }


def _collect_account_sync(account: dict[str, Any], start_page: int, max_page: int) -> dict[str, Any]:
    interval = runtime_settings.get_int_sync("interval", 60)
    return collect_wechat_account_articles(
        account,
        on_article=UpdateArticle,
        on_finish=Update_Over,
        start_page=start_page,
        max_page=max_page,
        interval=interval,
    )


async def _update_account_fetch_metadata(account_id: str, result: dict[str, Any]) -> None:
    articles = result.get("articles") if isinstance(result, dict) else []
    if not isinstance(articles, list):
        articles = []
    update_data: dict[str, Any] = {
        "last_fetch": _now(),
        "updated_at": _now(),
    }
    last_publish = _max_publish_time_iso(articles)
    if last_publish:
        update_data["last_publish"] = last_publish
    await wechat_account_repo.update_wechat_account(account_id, update_data)


async def _execute_collection_item(item: dict[str, Any]) -> None:
    item_id = str(item.get("id") or "")
    run_id = str(item.get("run_id") or "")
    account_id = str(item.get("wechat_account_id") or "")
    if not item_id or not run_id or not account_id:
        logger.error(f"[article-collection.worker] invalid item payload={item}")
        return

    account = await wechat_account_repo.get_wechat_account_by_id(account_id)
    if not account:
        account = item.get("account_snapshot") if isinstance(item.get("account_snapshot"), dict) else None
    if not account:
        raise ValueError("公众号不存在，无法采集")

    start_page = int(item.get("start_page") or 0)
    max_page = int(item.get("max_page") or 1)
    result = await asyncio.to_thread(_collect_account_sync, account, start_page, max_page)
    count = int((result or {}).get("count") or 0)
    await _update_account_fetch_metadata(account_id, result or {})
    await article_collection_repo.update_item(
        item_id,
        {
            "status": "success",
            "articles_count": count,
            "error": "",
            "finished_at": _now(),
            "locked_at": None,
            "locked_by": None,
        },
    )
    await _refresh_run_summary(run_id)


async def _article_collection_worker_loop(worker_id: str, stop_event: asyncio.Event) -> None:
    logger.info(f"[article-collection.worker] started worker_id={worker_id}")
    while not stop_event.is_set():
        try:
            stale_before = (
                datetime.now(timezone.utc) - timedelta(minutes=STALE_PROCESSING_MINUTES)
            ).isoformat()
            item = await article_collection_repo.claim_next_item(
                worker_id=worker_id,
                stale_before=stale_before,
            )
            if not item:
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=WORKER_POLL_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    pass
                continue
            try:
                await _execute_collection_item(item)
            except Exception as exc:
                logger.exception(
                    f"[article-collection.worker] item failed item_id={item.get('id')}: {exc}"
                )
                await article_collection_repo.update_item(
                    str(item.get("id") or ""),
                    {
                        "status": "failed",
                        "error": str(exc),
                        "finished_at": _now(),
                        "locked_at": None,
                        "locked_by": None,
                    },
                )
                await _refresh_run_summary(str(item.get("run_id") or ""))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                f"[article-collection.worker] loop error worker_id={worker_id}: {exc}"
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=WORKER_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
    logger.info(f"[article-collection.worker] stopped worker_id={worker_id}")


async def start_article_collection_workers() -> None:
    global _worker_stop_event
    if not WORKER_ENABLED:
        logger.info("[article-collection.worker] disabled by ARTICLE_COLLECTION_WORKER_ENABLED")
        return
    if _worker_tasks:
        return

    _worker_stop_event = asyncio.Event()
    base_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    for index in range(WORKER_CONCURRENCY):
        worker_id = f"{base_id}-{index + 1}"
        _worker_tasks.append(
            asyncio.create_task(
                _article_collection_worker_loop(worker_id, _worker_stop_event),
                name=f"article-collection-worker-{index + 1}",
            )
        )
    logger.info(
        f"[article-collection.worker] started workers count={len(_worker_tasks)} "
        f"poll_interval={WORKER_POLL_INTERVAL_SECONDS}s"
    )


async def stop_article_collection_workers() -> None:
    global _worker_stop_event
    if _worker_stop_event:
        _worker_stop_event.set()
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
        _worker_tasks.clear()
    _worker_stop_event = None
