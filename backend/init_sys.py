import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

from core.integrations.supabase.auth import auth_manager
from core.profiles import profile_repo
from core.common.log import logger


async def init_user():
    """使用 Supabase Auth 初始化管理员账户"""

    username: str = os.getenv("USERNAME", "admin@example.com")
    password: str = os.getenv("PASSWORD", "admin@123")
    user_id: str | None = None

    try:
        result = await auth_manager.sign_up(
            email=username,
            password=password,
            user_metadata={"username": username},
        )
        user = result.get("user")
        user_id = str(getattr(user, "id", "") or "") or None

        logger.info(f"初始化 Supabase Auth 用户成功, 请使用以下凭据登录：{username}")
    except Exception as e:
        msg = str(e)
        if "User already registered" in msg or "already exists" in msg:
            logger.info(f"Supabase Auth 中已存在用户：{username}，跳过创建")
            try:
                service_client = auth_manager.get_client(use_service=True)
                page = service_client.auth.admin.list_users()
                users = getattr(page, "users", None) or []
                for user in users:
                    if getattr(user, "email", None) == username:
                        user_id = str(getattr(user, "id", "") or "") or None
                        break
            except Exception as lookup_err:
                logger.warning(f"查询已存在管理员用户失败: {lookup_err}")
        else:
            logger.error(f"Init error: {msg}")

    if user_id:
        await profile_repo.upsert_profile(
            user_id,
            {
                "username": username,
                "nickname": username,
                "role": "admin",
                "status": "active",
            },
        )
        logger.info(f"管理员 profile 已初始化: {username}")


def sync_models():
    """同步模型到表结构"""
    logger.info("使用Supabase, 表结构通过迁移管理, 跳过模型同步")
    pass


async def init():
    sync_models()
    await init_user()


if __name__ == "__main__":
    asyncio.run(init())
