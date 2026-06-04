from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class ActivityCreate(BaseModel):
    article_id: str
    article_url: Optional[str] = None
    title: str = ""
    original_title: str = ""
    registration_time_text: str = ""
    registration_method: Optional[str] = None
    event_time_text: str = ""
    event_fee: str = "无"
    audience: str = "无"
    status: str = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ActivityUpdate(BaseModel):
    title: Optional[str] = None
    original_title: Optional[str] = None
    registration_time_text: Optional[str] = None
    registration_method: Optional[str] = None
    event_time_text: Optional[str] = None
    event_fee: Optional[str] = None
    audience: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
