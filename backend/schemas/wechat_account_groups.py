from datetime import datetime, time as dt_time
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class WeChatAccountGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    intro: Optional[str] = None
    cover: Optional[str] = None
    wechat_account_ids: Optional[str] = None
    status: Optional[int] = None


class WeChatAccountGroupScheduleUpdate(BaseModel):
    enabled: bool
    time: dt_time | None = None
    collection_pages: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def require_time_when_enabled(self):
        if self.enabled and self.time is None:
            raise ValueError("启用定时采集时必须设置执行时间")
        return self


class WeChatAccountGroup(WeChatAccountGroupCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    schedule_enabled: bool = False
    schedule_time: Optional[dt_time] = None
    collection_pages: int = 1
    last_scheduled_date: Optional[str] = None
    last_scheduled_at: Optional[datetime] = None
    last_collection_run_id: Optional[str] = None
    last_schedule_error: str = ""

    class Config:
        from_attributes = True
