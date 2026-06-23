from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from core.articles.collection_service import enqueue_group_collection
from core.common.log import logger
from core.wechat_account_groups import wechat_account_group_repo


SCHEDULE_TIMEZONE = ZoneInfo("Asia/Shanghai")
SCHEDULE_POLL_SECONDS = 30

_scheduler_task: asyncio.Task[None] | None = None
_scheduler_stop_event: asyncio.Event | None = None


async def run_schedule_tick(
    *,
    now: datetime | None = None,
    repo=wechat_account_group_repo,
    enqueue: Callable[..., Awaitable[dict[str, Any]]] = enqueue_group_collection,
) -> None:
    local_now = (now or datetime.now(SCHEDULE_TIMEZONE)).astimezone(
        SCHEDULE_TIMEZONE
    )
    today = local_now.date().isoformat()
    current_time = local_now.strftime("%H:%M")

    for group in await repo.get_enabled_schedules():
        configured = str(group.get("schedule_time") or "")[:5]
        last_scheduled_date = str(group.get("last_scheduled_date") or "")
        if configured != current_time or last_scheduled_date == today:
            continue

        group_id = str(group.get("id") or "")
        if not group_id:
            continue

        await repo.mark_schedule_attempt(
            group_id,
            {
                "last_scheduled_date": today,
                "last_scheduled_at": local_now.isoformat(),
            },
        )
        try:
            result = await enqueue(
                group_id,
                start_page=0,
                max_page=int(group.get("collection_pages") or 1),
            )
            await repo.mark_schedule_attempt(
                group_id,
                {
                    "last_collection_run_id": result.get("run_id"),
                    "last_schedule_error": "",
                },
            )
        except Exception as exc:
            logger.error(f"分组定时采集入队失败 group_id={group_id}: {exc}")
            await repo.mark_schedule_attempt(
                group_id,
                {"last_schedule_error": str(exc)[:1000]},
            )


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await run_schedule_tick()
        except Exception as exc:
            logger.error(f"公众号分组调度检查失败: {exc}")
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=SCHEDULE_POLL_SECONDS
            )
        except TimeoutError:
            pass


async def start_group_collection_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.create_task(
        _scheduler_loop(_scheduler_stop_event),
        name="group-collection-scheduler",
    )


async def stop_group_collection_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    task = _scheduler_task
    if task is None:
        return
    if _scheduler_stop_event is not None:
        _scheduler_stop_event.set()
    await task
    _scheduler_task = None
    _scheduler_stop_event = None
