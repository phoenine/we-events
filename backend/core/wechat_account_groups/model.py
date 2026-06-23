from typing import Any, Optional
from pydantic import BaseModel


class WeChatAccountGroup(BaseModel):
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    intro: Optional[str] = None
    cover: Optional[str] = None
    status: Optional[int] = 1
    schedule_enabled: bool = False
    schedule_time: Optional[str] = None
    collection_pages: int = 1
    last_scheduled_date: Optional[str] = None
    last_scheduled_at: Optional[str] = None
    last_collection_run_id: Optional[str] = None
    last_schedule_error: str = ""
    last_collection_run: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None   # ISO datetime string
    updated_at: Optional[str] = None   # ISO datetime string
