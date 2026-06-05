from typing import Any, Callable, Optional

from core.integrations.wx import create_gather
from core.common.log import logger
from core.common.runtime_settings import runtime_settings


def _account_value(account: Any, key: str) -> Any:
    if isinstance(account, dict):
        return account.get(key)
    return getattr(account, key, None)


def collect_wechat_account_articles(
    account: Any,
    *,
    on_article: Optional[Callable[..., Any]] = None,
    on_finish: Optional[Callable[..., Any]] = None,
    start_page: int = 0,
    max_page: int = 1,
    interval: Optional[int] = None,
) -> dict[str, Any]:
    """采集单个公众号文章并返回结果。"""
    faker_id = _account_value(account, "faker_id")
    wechat_account_id = _account_value(account, "id")
    account_name = _account_value(account, "mp_name") or _account_value(account, "name")

    if not faker_id:
        raise ValueError("公众号缺少 faker_id, 无法采集")

    wx = create_gather()
    gather_content = runtime_settings.get_bool_sync("gather.content", True)
    gather_mode = runtime_settings.get_sync("gather.model", "app")
    logger.info(
        f"[collect-wechat-account] wechat_account_id={wechat_account_id} mode={gather_mode} gather_content={gather_content} "
        f"start_page={start_page} max_page={max_page}"
    )
    try:
        wx.get_Articles(
            faker_id,
            wechat_account_id=wechat_account_id,
            wechat_account_name=account_name,
            CallBack=on_article,
            Over_CallBack=on_finish,
            start_page=start_page,
            MaxPage=max_page,
            interval=interval if interval is not None else 0,
            Gather_Content=gather_content,
        )
    except Exception as e:
        logger.error(f"采集公众号[{account_name or wechat_account_id}]失败: {e}")
        raise

    return {
        "wechat_account_id": wechat_account_id,
        "wechat_account_name": account_name,
        "articles": wx.articles,
        "count": wx.all_count(),
    }
