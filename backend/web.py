from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from apis.auth import router as auth_router
from apis.user import router as user_router
from apis.article import router as article_router
from apis.wechat_accounts import router as wx_router
from apis.config_management import router as config_router
from apis.sys_info import router as sys_info_router
from apis.wechat_account_groups import router as wechat_account_groups_router
from apis.activities import router as activities_router

from core.common.app_settings import settings
from core.common.log import configure_logger
from core.common.base import VERSION, API_BASE
from core.articles.collection_service import (
    start_article_collection_workers,
    stop_article_collection_workers,
)
from core.activities.service import (
    start_activity_extraction_workers,
    stop_activity_extraction_workers,
)

configure_logger(level=settings.log_level, log_file=settings.log_file)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_article_collection_workers()
    await start_activity_extraction_workers()
    try:
        yield
    finally:
        await stop_activity_extraction_workers()
        await stop_article_collection_workers()


app = FastAPI(
    title="we-events API",
    description="微信公众号文章采集服务API文档",
    version="1.0.0",
    docs_url="/api/docs",  # 指定文档路径
    redoc_url="/api/redoc",  # 指定Redoc路径
    # 指定OpenAPI schema路径
    openapi_url="/api/openapi.json",
    openapi_tags=[
        {
            "name": "认证",
            "description": "用户认证相关接口",
        }
    ],
    swagger_ui_parameters={
        "persistAuthorization": True,
        "withCredentials": True,
    },
    lifespan=lifespan,
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_custom_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Version"] = VERSION
    response.headers["X-Powered-By"] = "Phoenine"
    response.headers["GITHUB"] = "https://github.com/phoenine/we-events"
    response.headers["Server"] = settings.app_name
    return response


# 创建API路由分组
api_router = APIRouter(prefix=f"{API_BASE}")
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(article_router)
api_router.include_router(wx_router)
api_router.include_router(config_router)
api_router.include_router(sys_info_router)
api_router.include_router(wechat_account_groups_router)
api_router.include_router(activities_router)

# 注册API路由分组
app.include_router(api_router)
