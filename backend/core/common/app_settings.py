from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except Exception:
        return default


@dataclass(frozen=True)
class AppSettings:
    app_name: str
    server_name: str
    web_name: str
    enable_job: bool
    auto_reload: bool
    threads: int
    port: int
    debug: bool
    log_level: str
    log_file: str
    cache_dir: str
    safe_lic_key: str
    user_agent: str


def load_app_settings() -> AppSettings:
    return AppSettings(
        app_name=os.getenv("APP_NAME", "wx-harvester"),
        server_name=os.getenv("SERVER_NAME", "wx-harvester"),
        web_name=os.getenv("WEB_NAME", "WxHarvester微信公众号采集助手"),
        enable_job=_as_bool(os.getenv("ENABLE_JOB"), True),
        auto_reload=_as_bool(os.getenv("AUTO_RELOAD"), False),
        threads=max(1, _as_int(os.getenv("THREADS"), 1)),
        port=_as_int(os.getenv("PORT"), 38001),
        debug=_as_bool(os.getenv("DEBUG"), False),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        log_file=os.getenv("LOG_FILE", "./data/logs/wx-harvester.log"),
        cache_dir=os.getenv("CACHE_DIR", "data/cache"),
        safe_lic_key=os.getenv("SAFE_LIC_KEY", "PHOENINE-SECURE-LIC-KEY-1234567890"),
        user_agent=os.getenv(
            "USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36/WeRss",
        ),
    )


settings = load_app_settings()
