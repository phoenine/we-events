from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ArticleBase(BaseModel):
    id: str
    mp_id: Optional[str] = None
    title: Optional[str] = None
    pic_url: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    content_fetch_status: Optional[str] = None
    content_fetch_error: Optional[str] = None
    activity_extraction_status: Optional[str] = None
    activity_extraction_error: Optional[str] = None
    publish_time: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Article(ArticleBase):
    content: Optional[str] = None
    content_md: Optional[str] = None
