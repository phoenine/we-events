from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ActivityCreate(BaseModel):
    article_id: str
    source_wechat_account_id: Optional[str] = None
    article_url: Optional[str] = None
    title: str = ""
    original_title: str = ""
    registration_time_text: str = ""
    registration_method: Optional[str] = None
    event_time_text: str = ""
    event_fee: str = "无"
    audience: str = "无"
    status: str = "active"
    extraction_status: str = "reviewed"
    fallback_reason: Optional[str] = None
    confidence: Optional[float] = None
    extracted_by: str = "manual"
    extraction_model: Optional[str] = None
    extraction_raw: dict[str, Any] = Field(default_factory=dict)
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ActivityUpdate(BaseModel):
    source_wechat_account_id: Optional[str] = None
    article_url: Optional[str] = None
    title: Optional[str] = None
    original_title: Optional[str] = None
    registration_time_text: Optional[str] = None
    registration_method: Optional[str] = None
    event_time_text: Optional[str] = None
    event_fee: Optional[str] = None
    audience: Optional[str] = None
    status: Optional[str] = None
    extraction_status: Optional[str] = None
    fallback_reason: Optional[str] = None
    confidence: Optional[float] = None
    extracted_by: Optional[str] = None
    extraction_model: Optional[str] = None
    extraction_raw: Optional[dict[str, Any]] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
