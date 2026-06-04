from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Activity(BaseModel):
    id: Optional[str] = None
    article_id: str = ""
    source_wechat_account_id: Optional[str] = None
    article_url: str = ""

    title: str = ""
    original_title: str = ""
    registration_time_text: str = ""
    registration_method: str = ""
    event_time_text: str = ""
    event_fee: str = "无"
    audience: str = "无"
    status: str = "active"
    extraction_status: str = "extracted"
    fallback_reason: Optional[str] = None
    confidence: Optional[float] = None
    extracted_by: str = "llm"
    extraction_model: Optional[str] = None
    extraction_raw: dict = Field(default_factory=dict)
    reviewed_at: Optional[str] = None

    created_at: Optional[str] = None   # ISO datetime string when stored in Supabase
    updated_at: Optional[str] = None
