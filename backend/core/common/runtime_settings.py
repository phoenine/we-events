from __future__ import annotations

import os
from typing import Any

from core.common.app_settings import settings
from core.common.log import logger
from core.common.utils.async_tools import run_sync
from core.integrations.supabase.config_store import config_store


class RuntimeSettings:
    """运行时配置读取器，优先从数据库读取，失败回退到环境变量"""

    async def get(self, key: str, default: Any = None) -> Any:
        try:
            row = await config_store.get(key)
            if row and row.get("config_value") is not None:
                return row.get("config_value")
        except Exception as e:
            logger.warning(f"读取运行时配置失败，回退本地配置 key={key}: {e}")
        fallback = self._fallback_value(key, default)
        return fallback

    def _fallback_value(self, key: str, default: Any) -> Any:
        fallback_map: dict[str, Any] = {
            "max_page": os.getenv("MAX_PAGE", default),
            "sync_interval": os.getenv("SYNC_INTERVAL", default),
            "interval": os.getenv("SPAN_INTERVAL", default),
            "gather.content": os.getenv("GATHER_CONTENT", default),
            "gather.model": os.getenv("GATHER_MODEL", default),
            "collection.max_article_age_days": os.getenv("COLLECTION_MAX_ARTICLE_AGE_DAYS", default),
            "collection.repair_failed_existing": os.getenv("COLLECTION_REPAIR_FAILED_EXISTING", default),
            "collection.max_attempts": os.getenv("COLLECTION_MAX_ATTEMPTS", default),
            "image.retry_count": os.getenv("IMAGE_RETRY_COUNT", default),
        }
        return fallback_map.get(key, default)

    async def get_int(self, key: str, default: int) -> int:
        value = await self.get(key, default)
        try:
            return int(value)
        except Exception:
            return int(default)

    async def get_bool(self, key: str, default: bool) -> bool:
        value = await self.get(key, default)
        if isinstance(value, bool):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def get_sync(self, key: str, default: Any = None) -> Any:
        return run_sync(self.get(key, default))

    def get_int_sync(self, key: str, default: int):
        return run_sync(self.get_int(key, default))

    def get_bool_sync(self, key: str, default: bool):
        return run_sync(self.get_bool(key, default))


runtime_settings = RuntimeSettings()
