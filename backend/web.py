from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from apis.auth import router as auth_router
from apis.user import router as user_router
from apis.article import router as article_router
from apis.wechat_accounts import router as wx_router, legacy_router as wx_legacy_router
from apis.res import router as res_router
from apis.config_management import router as config_router
from apis.message_task import router as task_router
from apis.sys_info import router as sys_info_router
from apis.tags import router as tags_router
from apis.activities import router as activities_router

from core.common.app_settings import settings
from core.common.log import configure_logger
from core.common.base import VERSION, API_BASE
from core.common.utils import TaskQueue

configure_logger(level=settings.log_level, log_file=settings.log_file)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时启动后台任务队列
    TaskQueue.run_task_background()
    try:
        yield
    finally:
        # 应用关闭时停止并清理任务队列
        TaskQueue.stop()
        TaskQueue.clear_queue()


app = FastAPI(
    title="WxHarvester API",
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
    response.headers["GITHUB"] = "https://github.com/phoenine/wechat-events-harvester"
    response.headers["Server"] = settings.app_name
    return response


# 创建API路由分组
api_router = APIRouter(prefix=f"{API_BASE}")
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(article_router)
api_router.include_router(wx_router)
api_router.include_router(wx_legacy_router)
api_router.include_router(config_router)
api_router.include_router(task_router)
api_router.include_router(sys_info_router)
api_router.include_router(tags_router)
api_router.include_router(activities_router)

resource_router = APIRouter(prefix="/static")
resource_router.include_router(res_router)
# 注册API路由分组
app.include_router(api_router)
app.include_router(resource_router)
