from typing import Optional, List, Any

from jobs.article import UpdateArticle, Update_Over
from core.wechat_accounts import wechat_account_repo
from core.wechat_accounts.collector import collect_wechat_account_articles
from core.common.log import logger
from core.common.runtime_settings import runtime_settings
from core.common.utils import TaskQueue


def fetch_all_article():
    logger.info("开始更新")
    total_count = 0
    all_articles = []
    try:
        # 获取公众号列表（使用Supabase，同步接口）
        mps = wechat_account_repo.sync_get_wechat_accounts()
        for item in mps:
            try:
                result = collect_wechat_account_articles(
                    item,
                    on_article=UpdateArticle,
                    max_page=1,
                )
                total_count += int(result.get("count", 0))
                all_articles.extend(result.get("articles") or [])
            except Exception as e:
                logger.error(e)
        logger.info(all_articles)
    except Exception as e:
        logger.error(e)
    finally:
        logger.info(f"所有公众号更新完成,共更新{total_count}条数据")


def do_job(mp: Any = None) -> None:
    logger.info("执行公众号采集任务")
    count = 0
    mp_name = getattr(mp, "mp_name", None) or getattr(mp, "name", None) or (
        (mp.get("mp_name") or mp.get("name")) if isinstance(mp, dict) else None
    )
    try:
        interval = runtime_settings.get_int_sync("interval", 60)
        result = collect_wechat_account_articles(
            mp,
            on_article=UpdateArticle,
            on_finish=Update_Over,
            max_page=1,
            interval=interval,
        )
        count = int(result.get("count", 0))
    except Exception as e:
        logger.error(e)
    finally:
        logger.success(f"公众号[{mp_name}]采集完成,{count}成功条数")


def add_job(
    accounts: Optional[List[Any]] = None,
    isTest: bool = False,
) -> None:
    if isTest:
        TaskQueue.clear_queue()
    for account in accounts or []:
        # 兼容 dict / 对象两种形式，安全获取名称
        mp_name = getattr(account, "mp_name", None) or getattr(account, "name", None) or (
            (account.get("mp_name") or account.get("name")) if isinstance(account, dict) else "未知公众号"
        )

        TaskQueue.add_task(do_job, account)
        if isTest:
            logger.info(f"测试任务，{mp_name}，加入队列成功")
            break
        logger.info(f"{mp_name}，加入队列成功")
    logger.success(TaskQueue.get_queue_info())


def get_wechat_accounts(account_ids: Optional[List[str]] = None) -> Optional[List[Any]]:
    if account_ids:
        accounts = wechat_account_repo.sync_get_wechat_accounts_by_ids(account_ids)
        if accounts:
            return accounts
    return wechat_account_repo.sync_get_wechat_accounts()


def start_all_task():
    # 开启自动同步未同步文章任务。公众号批量采集由 API/CLI 显式触发。
    from jobs.fetch_no_article import start_sync_content

    start_sync_content()


if __name__ == "__main__":
    # do_job()
    # start_all_task()
    pass
