from __future__ import annotations

import asyncio
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from core.articles import article_collection_repo
from core.common.log import logger
from core.common.runtime_settings import runtime_settings
from core.wechat_accounts import wechat_account_repo
from core.wechat_account_groups import wechat_account_group_repo
from core.wechat_accounts.collector import collect_wechat_account_articles
from jobs.article import UpdateArticle, Update_Over


# The shared WeChat MP session is global. Article collection must therefore be
# globally serial even when more than one backend process is accidentally alive.
WECHAT_MP_SESSION_SERIAL_REASON = "shared WeChat MP session is global"
STALE_PROCESSING_MINUTES = int(os.getenv("ARTICLE_COLLECTION_STALE_MINUTES", "45"))
STALE_QUEUED_HOURS = int(os.getenv("ARTICLE_COLLECTION_QUEUED_STALE_HOURS", "24"))
WORKER_ENABLED = os.getenv("ARTICLE_COLLECTION_WORKER_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
}
WORKER_POLL_INTERVAL_SECONDS = max(
    1.0,
    float(os.getenv("ARTICLE_COLLECTION_POLL_INTERVAL_SECONDS", "3")),
)

_worker_tasks: list[asyncio.Task[None]] = []
_worker_stop_event: asyncio.Event | None = None


WechatErrorCategory = Literal[
    "not_logged_in",
    "invalid_session",
    "session_reuse_error",
    "environment_blocked",
    "frequency_control",
    "request_error",
    "unknown",
]


@dataclass(frozen=True)
class WechatSessionDiagnostics:
    persisted_session_exists: bool
    persisted_cookie_count: int
    cookie_header_present: bool
    session_cookie_count: int
    persisted_token_exists: bool
    has_user_agent: bool


class WechatCollectionError(Exception):
    def __init__(
        self,
        message: str,
        *,
        category: WechatErrorCategory = "unknown",
        retryable: bool = False,
        diagnostics: WechatSessionDiagnostics | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.diagnostics = diagnostics


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


def _is_stale_queued_item(item: dict[str, Any]) -> bool:
    if item.get("status") != "queued":
        return False
    queued_at = _parse_datetime(item.get("queued_at") or item.get("created_at"))
    if not queued_at:
        return False
    return datetime.now(timezone.utc) - queued_at > timedelta(hours=STALE_QUEUED_HOURS)


async def _expire_stale_queued_item(item: dict[str, Any]) -> bool:
    if _is_stale_queued_item(item):
        await _mark_item_stale_failed(item)
        return True
    return False


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


def _failed_item_update(item: dict[str, Any], error: str) -> dict[str, Any]:
    attempt_count = int(item.get("attempt_count") or 0)
    max_attempts = max(1, int(item.get("max_attempts") or 1))
    if attempt_count < max_attempts:
        return {
            "status": "queued",
            "error": error,
            "locked_at": None,
            "locked_by": None,
        }
    return {
        "status": "failed",
        "error": error,
        "finished_at": _now(),
        "locked_at": None,
        "locked_by": None,
    }


def _wechat_session_diagnostics() -> WechatSessionDiagnostics:
    try:
        from driver.session.store import Store

        session = Store.load_session()
    except Exception:
        session = None
    if not isinstance(session, dict):
        session = {}

    cookies = session.get("cookies")
    if not isinstance(cookies, list):
        cookies = []
    cookies_str = str(session.get("cookies_str") or "")
    return WechatSessionDiagnostics(
        persisted_session_exists=bool(session),
        persisted_cookie_count=len(cookies),
        cookie_header_present=bool(cookies_str),
        session_cookie_count=len(cookies),
        persisted_token_exists=bool(session.get("token")),
        has_user_agent=bool(session.get("user_agent")),
    )


def _is_collection_worker_ready() -> bool:
    diagnostics = _wechat_session_diagnostics()
    return bool(
        diagnostics.cookie_header_present
        or diagnostics.persisted_cookie_count > 0
    )


def _format_session_diagnostics(diagnostics: WechatSessionDiagnostics | None) -> str:
    if not diagnostics:
        return ""
    return (
        " persisted_session_exists="
        f"{diagnostics.persisted_session_exists}"
        f" persisted_cookie_count={diagnostics.persisted_cookie_count}"
        f" cookie_header_present={diagnostics.cookie_header_present}"
        f" session_cookie_count={diagnostics.session_cookie_count}"
        f" persisted_token_exists={diagnostics.persisted_token_exists}"
        f" has_user_agent={diagnostics.has_user_agent}"
    )


def _classify_collection_exception(exc: Exception) -> WechatCollectionError:
    if isinstance(exc, WechatCollectionError):
        return exc

    message = str(exc) or exc.__class__.__name__
    lower_message = message.lower()
    if "代码:200003" in message or "invalid session" in lower_message:
        return WechatCollectionError(message, category="invalid_session")
    if "请先扫码登录公众号平台" in message:
        diagnostics = _wechat_session_diagnostics()
        if diagnostics.persisted_session_exists and (
            diagnostics.persisted_cookie_count > 0 or diagnostics.persisted_token_exists
        ):
            return WechatCollectionError(
                message,
                category="session_reuse_error",
                diagnostics=diagnostics,
            )
        return WechatCollectionError(
            message,
            category="not_logged_in",
            diagnostics=diagnostics,
        )
    if any(
        keyword in lower_message
        for keyword in ("captcha", "environment", "verify", "risk control")
    ) or any(keyword in message for keyword in ("当前环境异常", "完成验证", "验证码")):
        return WechatCollectionError(message, category="environment_blocked")
    if any(keyword in lower_message for keyword in ("frequency", "frequencey")) or any(
        keyword in message for keyword in ("频控", "访问频繁")
    ):
        return WechatCollectionError(message, category="frequency_control", retryable=True)
    return WechatCollectionError(message, category="unknown")


def _terminal_session_error_message(error: WechatCollectionError) -> str:
    if error.category in {"not_logged_in", "invalid_session"}:
        return "微信登录态已失效，请重新扫码登录"
    if error.category == "environment_blocked":
        return "微信环境验证拦截，本轮剩余账号已跳过"
    if error.category == "frequency_control":
        return "微信访问频控，本轮剩余账号已跳过"
    return str(error)


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
    item_statuses = [
        {
            "item_id": item.get("id"),
            "wechat_account_id": item.get("wechat_account_id"),
            "status": item.get("status"),
            "attempt_count": item.get("attempt_count"),
            "articles_count": item.get("articles_count"),
            "error": str(item.get("error") or "")[:200],
        }
        for item in items
    ]
    logger.info(
        f"[article-collection.run-summary] run_id={run_id} status={status} "
        f"total={total} success={success} failed={failed} skipped={skipped} "
        f"active={active} articles_count={articles_count} items={item_statuses}"
    )
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
        if await _expire_stale_queued_item(active_item):
            pass
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

    max_attempts = max(1, await runtime_settings.get_int("collection.max_attempts", 2))
    try:
        item = await article_collection_repo.create_item(
            {
                "run_id": run_id,
                "wechat_account_id": wechat_account_id,
                "account_snapshot": account,
                "start_page": start_page,
                "max_page": max_page,
                "max_attempts": max_attempts,
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
    found_account_ids = {str(account.get("id") or "") for account in accounts}
    missing_account_ids = [
        account_id for account_id in account_ids if str(account_id) not in found_account_ids
    ]
    logger.info(
        f"[group-collection.plan] group_id={group_id} requested_account_ids={account_ids} "
        f"found_account_ids={sorted(found_account_ids)} missing_account_ids={missing_account_ids}"
    )
    runnable: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for account in accounts:
        account_id = str(account.get("id") or "")
        if not account_id:
            logger.info(
                f"[group-collection.plan] group_id={group_id} decision=skip_missing_id "
                f"account={account}"
            )
            continue
        if _is_account_disabled(account):
            logger.info(
                f"[group-collection.plan] group_id={group_id} account_id={account_id} "
                f"decision=skip_disabled status={account.get('status')}"
            )
            skipped.append({"id": account_id, "reason": "disabled"})
            continue
        active_item = await article_collection_repo.get_latest_active_item_by_account(
            account_id
        )
        if active_item:
            if await _expire_stale_queued_item(active_item):
                logger.info(
                    f"[group-collection.plan] group_id={group_id} account_id={account_id} "
                    f"decision=mark_stale_queued_failed active_item_id={active_item.get('id')} "
                    f"active_status={active_item.get('status')}"
                )
            else:
                logger.info(
                    f"[group-collection.plan] group_id={group_id} account_id={account_id} "
                    f"decision=skip_already_running active_item_id={active_item.get('id')} "
                    f"run_id={active_item.get('run_id')} active_status={active_item.get('status')}"
                )
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
            logger.info(
                f"[group-collection.plan] group_id={group_id} account_id={account_id} "
                f"decision=skip_cooldown time_span={time_span} sync_interval={sync_interval} "
                f"last_fetch={account.get('last_fetch')} sync_time={account.get('sync_time')} "
                f"update_time={account.get('update_time')}"
            )
            skipped.append(
                {
                    "id": account_id,
                    "reason": "cooldown",
                    "time_span": time_span,
                    "sync_interval": sync_interval,
                }
            )
            continue
        logger.info(
            f"[group-collection.plan] group_id={group_id} account_id={account_id} "
            f"decision=runnable time_span={time_span} sync_interval={sync_interval} "
            f"last_fetch={account.get('last_fetch')} sync_time={account.get('sync_time')} "
            f"update_time={account.get('update_time')}"
        )
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
    max_attempts = max(1, await runtime_settings.get_int("collection.max_attempts", 2))
    for account in runnable:
        account_id = str(account.get("id") or "")
        try:
            item = await article_collection_repo.create_item(
                {
                    "run_id": run_id,
                    "wechat_account_id": account_id,
                    "account_snapshot": account,
                    "start_page": start_page,
                    "max_page": max_page,
                    "max_attempts": max_attempts,
                }
            )
            created.append(item)
            logger.info(
                f"[group-collection.enqueue-item] group_id={group_id} run_id={run_id} "
                f"item_id={item.get('id')} account_id={account_id} max_attempts={max_attempts}"
            )
        except Exception as exc:
            logger.exception(
                f"[group-collection.enqueue-item] create failed group_id={group_id} "
                f"run_id={run_id} account_id={account_id}: {exc}"
            )
            skipped.append(
                {"id": account_id, "reason": "create_item_failed", "error": str(exc)}
            )

    await article_collection_repo.update_run(
        run_id,
        {
            "total_items": len(created),
            "skipped_items": len(skipped),
            "status": "queued" if created else "success",
            **({"finished_at": _now()} if not created else {}),
        },
    )

    logger.info(
        f"[group-collection.enqueue] group_id={group_id} account_count={len(accounts)} "
        f"created={len(created)} skipped={len(skipped)} skipped_accounts={skipped}"
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
    logger.info(
        f"[article-collection.item] start run_id={run_id} item_id={item_id} "
        f"account_id={account_id} account_name={account.get('mp_name') or account.get('name')} "
        f"attempt_count={item.get('attempt_count')} max_attempts={item.get('max_attempts')} "
        f"start_page={start_page} max_page={max_page}"
    )
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
    logger.info(
        f"[article-collection.item] success run_id={run_id} item_id={item_id} "
        f"account_id={account_id} articles_count={count}"
    )


async def _execute_collection_run(run: dict[str, Any], *, worker_id: str) -> None:
    run_id = str(run.get("id") or "")
    if not run_id:
        logger.error(f"[article-collection.run] invalid run payload={run}")
        return

    items = await article_collection_repo.get_items_by_run(run_id)
    logger.info(
        f"[article-collection.run] start run_id={run_id} worker_id={worker_id} "
        f"item_count={len(items)} global_serial=True reason={WECHAT_MP_SESSION_SERIAL_REASON}"
    )
    should_stop = False

    for index, item in enumerate(items):
        if should_stop:
            break
        item_id = str(item.get("id") or "")
        if not item_id:
            logger.error(f"[article-collection.run] invalid item payload={item}")
            continue

        latest_item = await article_collection_repo.get_item_by_id(item_id)
        if latest_item:
            item = latest_item

        status = str(item.get("status") or "queued")
        if status not in {"queued", "processing"}:
            logger.info(
                f"[article-collection.run] skip item run_id={run_id} "
                f"item_id={item.get('id')} status={status}"
            )
            continue

        attempt_count = int(item.get("attempt_count") or 0) + 1
        current_item = {
            **item,
            "status": "processing",
            "attempt_count": attempt_count,
            "locked_by": worker_id,
        }
        await article_collection_repo.update_item(
            item_id,
            {
                "status": "processing",
                "locked_at": _now(),
                "locked_by": worker_id,
                "started_at": _now(),
                "attempt_count": attempt_count,
                "error": "",
            },
        )

        try:
            await _execute_collection_item(current_item)
        except Exception as exc:
            error = _classify_collection_exception(exc)
            diagnostic_text = _format_session_diagnostics(error.diagnostics)
            log_message = (
                f"[article-collection.run] item failed run_id={run_id} item_id={item_id} "
                f"account_id={item.get('wechat_account_id')} category={error.category} "
                f"retryable={error.retryable}{diagnostic_text}: {error}"
            )
            if error.category == "unknown":
                logger.exception(log_message)
            else:
                logger.warning(log_message)
            if error.category == "session_reuse_error":
                await article_collection_repo.update_item(
                    item_id,
                    {
                        "status": "failed",
                        "error": f"微信登录态复用异常：{error}{diagnostic_text}",
                        "finished_at": _now(),
                        "locked_at": None,
                        "locked_by": None,
                    },
                )
                continue

            if error.category in {
                "not_logged_in",
                "invalid_session",
                "environment_blocked",
                "frequency_control",
            }:
                stop_message = _terminal_session_error_message(error)
                await article_collection_repo.update_item(
                    item_id,
                    {
                        "status": "failed",
                        "error": f"{stop_message}：{error}",
                        "finished_at": _now(),
                        "locked_at": None,
                        "locked_by": None,
                    },
                )
                for remaining in items[index + 1 :]:
                    if str(remaining.get("status") or "queued") not in {"queued", "processing"}:
                        continue
                    remaining_id = str(remaining.get("id") or "")
                    if not remaining_id:
                        continue
                    await article_collection_repo.update_item(
                        remaining_id,
                        {
                            "status": "failed",
                            "error": stop_message,
                            "finished_at": _now(),
                            "locked_at": None,
                            "locked_by": None,
                        },
                    )
                should_stop = True
                continue

            failed_update = _failed_item_update(current_item, str(error))
            logger.info(
                f"[article-collection.run] failure-update run_id={run_id} item_id={item_id} "
                f"account_id={item.get('wechat_account_id')} attempt_count={attempt_count} "
                f"max_attempts={item.get('max_attempts')} next_status={failed_update.get('status')} "
                f"error={str(error)[:300]}"
            )
            await article_collection_repo.update_item(item_id, failed_update)

    await _refresh_run_summary(run_id)


async def _article_collection_worker_loop(worker_id: str, stop_event: asyncio.Event) -> None:
    logger.info(f"[article-collection.worker] started worker_id={worker_id}")
    waiting_for_session = False
    while not stop_event.is_set():
        try:
            if not _is_collection_worker_ready():
                if not waiting_for_session:
                    logger.warning(
                        f"[article-collection.worker] waiting-for-session "
                        f"worker_id={worker_id}"
                    )
                    waiting_for_session = True
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=WORKER_POLL_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    pass
                continue
            if waiting_for_session:
                logger.info(
                    f"[article-collection.worker] session-ready worker_id={worker_id}"
                )
                waiting_for_session = False

            stale_before = (
                datetime.now(timezone.utc) - timedelta(minutes=STALE_PROCESSING_MINUTES)
            ).isoformat()
            run = await article_collection_repo.claim_next_run(
                worker_id=worker_id,
                stale_before=stale_before,
            )
            if not run:
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=WORKER_POLL_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    pass
                continue
            logger.info(
                f"[article-collection.worker] claimed-run worker_id={worker_id} "
                f"run_id={run.get('id')} scope={run.get('scope')} "
                f"total_items={run.get('total_items')} status={run.get('status')}"
            )
            await _execute_collection_run(run, worker_id=worker_id)
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
    worker_id = f"{base_id}-1"
    _worker_tasks.append(
        asyncio.create_task(
            _article_collection_worker_loop(worker_id, _worker_stop_event),
            name="article-collection-worker-1",
        )
    )
    logger.info(
        f"[article-collection.worker] started workers count={len(_worker_tasks)} "
        f"poll_interval={WORKER_POLL_INTERVAL_SECONDS}s global_serial=True "
        f"reason={WECHAT_MP_SESSION_SERIAL_REASON}"
    )


async def stop_article_collection_workers() -> None:
    global _worker_stop_event
    if _worker_stop_event:
        _worker_stop_event.set()
    if _worker_tasks:
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
        _worker_tasks.clear()
    _worker_stop_event = None
