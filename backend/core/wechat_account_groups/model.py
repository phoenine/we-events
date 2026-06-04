from typing import Optional
from pydantic import BaseModel


class WeChatAccountGroup(BaseModel):
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    intro: Optional[str] = None
    cover: Optional[str] = None
    status: Optional[int] = 1
    created_at: Optional[str] = None   # ISO datetime string
    updated_at: Optional[str] = None   # ISO datetime string
