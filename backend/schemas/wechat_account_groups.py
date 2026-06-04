from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class WeChatAccountGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    intro: Optional[str] = None
    cover: Optional[str] = None
    wechat_account_ids: Optional[str] = None
    status: Optional[int] = None


class WeChatAccountGroup(WeChatAccountGroupCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
