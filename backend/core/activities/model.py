from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Activity(BaseModel):
    id: str | None = None
    article_id: str = ""
    extraction_run_id: str | None = None
    source_wechat_account_id: str | None = None
    article_url: str = ""

    title: str = ""
    summary: str = ""
    event_time_text: str = ""
    start_at: str | None = None
    end_at: str | None = None
    event_status: str = "unknown"
    location_text: str = ""
    registration_text: str = ""
    registration_method: str = "unknown"
    registration_url: str = ""
    qr_image_urls: list[str] = Field(default_factory=list)
    fee_text: str = ""
    audience: str = ""
    review_status: str = "needs_review"
    confidence: float | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_activity: dict[str, Any] = Field(default_factory=dict)

    created_at: str | None = None
    updated_at: str | None = None
