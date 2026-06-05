from typing import Any, cast

from core.common.log import logger
from core.integrations.supabase.client import supabase_client
from core.integrations.supabase.settings import settings


class ConfigStore:
    """运行时配置存储（Supabase）"""

    TABLE_NAME = "config_managements"

    def __init__(self) -> None:
        self.client = supabase_client

    def available(self) -> bool:
        return bool(settings.url and settings.service_key)

    async def fetch_all(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        if not self.available():
            return []
        try:
            rows = await self.client.select(
                self.TABLE_NAME,
                columns="config_key,config_value,description,updated_at,created_at",
                order="updated_at",
                limit=limit,
                offset=offset,
            )
            return cast(list[dict[str, Any]], rows)
        except Exception as e:
            logger.error(f"读取配置列表失败: {e}")
            raise

    async def count(self) -> int:
        if not self.available():
            return 0
        try:
            return int(await self.client.count(self.TABLE_NAME))
        except Exception as e:
            logger.error(f"读取配置数量失败: {e}")
            raise

    async def get(self, config_key: str) -> dict[str, Any] | None:
        if not self.available():
            return None
        try:
            rows = await self.client.select(
                self.TABLE_NAME,
                filters={"config_key": config_key},
                columns="config_key,config_value,description,updated_at,created_at",
                limit=1,
            )
            return cast(dict[str, Any], rows[0]) if rows else None
        except Exception as e:
            logger.error(f"读取配置失败 key={config_key}: {e}")
            raise

    async def create(
        self,
        config_key: str,
        config_value: str,
        description: str = "",
    ) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("Supabase 不可用")
        try:
            row = await self.client.insert(
                self.TABLE_NAME,
                {
                    "config_key": config_key,
                    "config_value": config_value,
                    "description": description,
                },
            )
            return cast(dict[str, Any], row or {})
        except Exception as e:
            logger.error(f"创建配置失败 key={config_key}: {e}")
            raise

    async def update(
        self,
        config_key: str,
        config_value: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("Supabase 不可用")
        try:
            payload: dict[str, Any] = {"config_value": config_value}
            if description is not None:
                payload["description"] = description
            rows = await self.client.update(
                self.TABLE_NAME,
                payload,
                filters={"config_key": config_key},
            )
            return cast(dict[str, Any], rows[0]) if rows else {}
        except Exception as e:
            logger.error(f"更新配置失败 key={config_key}: {e}")
            raise

    async def delete(self, config_key: str) -> bool:
        if not self.available():
            raise RuntimeError("Supabase 不可用")
        try:
            rows = await self.client.delete(
                self.TABLE_NAME,
                filters={"config_key": config_key},
            )
            return bool(rows)
        except Exception as e:
            logger.error(f"删除配置失败 key={config_key}: {e}")
            raise


config_store = ConfigStore()
