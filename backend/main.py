import asyncio
import argparse
import uvicorn

from core.common.app_settings import settings
from core.common.log import configure_logger
from core.common.log import logger
from core.common.base import VERSION, API_BASE


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-init", help="初始化数据库,初始化用户", default=False)
    return parser.parse_known_args()[0]


def log_app_banner() -> None:
    logger.info(f"名称:{settings.app_name}\n版本:{VERSION} API_BASE:{API_BASE}")


if __name__ == "__main__":
    args = parse_args()
    configure_logger(level=settings.log_level, log_file=settings.log_file)
    log_app_banner()
    if args.init == "True":
        import init_sys as init

        asyncio.run(init.init())
    logger.info("启动服务器")
    auto_reload = settings.auto_reload
    workers = settings.threads
    if workers > 1:
        # Article collection uses a shared WeChat MP session. Multiple Uvicorn
        # worker processes would each start their own queue consumer and race on
        # the same persisted cookies, causing false "not logged in" failures.
        logger.warning("公众号采集依赖单一微信登录态，Uvicorn workers 已强制设为 1")
        workers = 1
    if auto_reload and workers > 1:
        logger.warning("AUTO_RELOAD=True 时 workers 必须为 1，已自动降为 1")
        workers = 1

    run_kwargs = {
        "app": "web:app",
        "host": "0.0.0.0",
        "port": settings.port,
        "workers": workers,
    }
    if auto_reload:
        run_kwargs.update(
            {
                "reload": True,
                "reload_dirs": ["apis", "core", "driver", "schemas"],
                "reload_excludes": ["data"],
            }
        )

    uvicorn.run(**run_kwargs)
    pass
