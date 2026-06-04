from typing import Optional
from pydantic import BaseModel


class WeChatAccount(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    status: Optional[int] = None
    last_publish: Optional[str] = None
    last_fetch: Optional[str] = None
    created_at: Optional[str] = None   # ISO datetime string
    updated_at: Optional[str] = None   # ISO datetime string
    faker_id: Optional[str] = None
