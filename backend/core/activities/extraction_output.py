from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator


REGISTRATION_METHODS = {"qr_code", "link", "phone", "wechat", "onsite", "none", "unknown"}
EVIDENCE_SOURCES = {"text", "image", "mixed"}


class ActivityEvidence(BaseModel):
    field: str = ""
    text: str = ""
    source: Literal["text", "image", "mixed"] = "mixed"
    image_urls: list[str] = Field(default_factory=list)

    @field_validator("field", "text", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: Any):
        return str(value or "").strip()

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: Any):
        text = str(value or "").strip().lower()
        return text if text in EVIDENCE_SOURCES else "mixed"

    @field_validator("image_urls", mode="before")
    @classmethod
    def normalize_image_urls(cls, value: Any):
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if value:
            return [str(value)]
        return []


class ExtractedActivity(BaseModel):
    title: str
    summary: str = ""
    event_time_text: str = ""
    start_at: str | None = None
    end_at: str | None = None
    location_text: str = ""
    registration_text: str = ""
    registration_method: str = "unknown"
    registration_url: str = ""
    qr_image_urls: list[str] = Field(default_factory=list)
    fee_text: str = ""
    audience: str = ""
    evidence: list[ActivityEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def title_required(cls, value: str):
        text = str(value or "").strip()
        if not text:
            raise ValueError("activity title is required")
        return text

    @field_validator(
        "summary",
        "event_time_text",
        "location_text",
        "registration_text",
        "registration_url",
        "fee_text",
        "audience",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: Any):
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("start_at", "end_at", mode="before")
    @classmethod
    def normalize_optional_datetime_text(cls, value: Any):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("registration_method", mode="before")
    @classmethod
    def normalize_registration_method(cls, value: Any):
        text = str(value or "").strip().lower()
        return text if text in REGISTRATION_METHODS else "unknown"

    @field_validator("qr_image_urls", "warnings", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any):
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if value:
            return [str(value)]
        return []

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_evidence(cls, value: Any):
        return value if isinstance(value, list) else []


class ActivityExtractionOutput(BaseModel):
    is_activity_article: bool = False
    confidence: float = 0
    reason: str = ""
    activities: list[ExtractedActivity] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any):
        try:
            confidence = float(value)
        except Exception:
            return 0.0
        if confidence > 1:
            confidence = confidence / 100
        return max(0.0, min(1.0, confidence))


def extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("LLM output is empty")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM output must be a JSON object")
    return data


def parse_activity_output(text: str) -> ActivityExtractionOutput:
    return ActivityExtractionOutput.model_validate(extract_json_object(text))


def parse_datetime(value: str | None):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def infer_start_at_from_event_text(
    event_time_text: str,
    *,
    reference_timestamp: int | None = None,
    timezone_name: str = "Asia/Shanghai",
) -> str | None:
    text = str(event_time_text or "").strip()
    if not text:
        return None

    match = re.search(r"(?:(?P<year>\d{4})\s*年\s*)?(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日?", text)
    if not match:
        match = re.search(r"(?P<month>\d{1,2})[./-](?P<day>\d{1,2})", text)
    if not match:
        return None

    tz = ZoneInfo(timezone_name)
    if reference_timestamp:
        reference = datetime.fromtimestamp(reference_timestamp, tz)
    else:
        reference = datetime.now(tz)

    year_text = match.groupdict().get("year")
    year = int(year_text) if year_text else reference.year
    month = int(match.group("month"))
    day = int(match.group("day"))

    try:
        candidate = datetime(year, month, day, tzinfo=tz)
    except ValueError:
        return None

    # Articles around year-end often mention January events without a year.
    # If the inferred date is far behind the article date, treat it as next year.
    if not year_text and (reference - candidate).days > 180:
        try:
            candidate = datetime(year + 1, month, day, tzinfo=tz)
        except ValueError:
            return None

    return candidate.isoformat()


def compute_event_status(start_at: str | None, end_at: str | None) -> str:
    now = datetime.now(timezone.utc)
    start = parse_datetime(start_at)
    end = parse_datetime(end_at)
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    local_tz = ZoneInfo("Asia/Shanghai")
    local_now = now.astimezone(local_tz)
    local_start = start.astimezone(local_tz) if start else None
    local_end = end.astimezone(local_tz) if end else None

    if local_start and local_now < local_start:
        return "upcoming"
    if local_end and local_now > local_end:
        return "ended"
    if local_start and not local_end:
        return "ongoing" if local_now.date() == local_start.date() else "ended"
    if local_start or local_end:
        return "ongoing"
    return "unknown"


REVIEW_RISK_KEYWORDS = (
    "不明确",
    "未明确",
    "缺失",
    "无法判断",
    "无法确定",
    "不确定",
    "待确认",
    "未提及",
    "没有提及",
    "未找到",
    "无法识别",
    "解析失败",
    "需要人工",
    "低置信度",
)


def has_review_risk(warnings: list[str]) -> bool:
    for warning in warnings:
        text = str(warning or "").strip()
        if text and any(keyword in text for keyword in REVIEW_RISK_KEYWORDS):
            return True
    return False


def compute_review_status(confidence: float, warnings: list[str]) -> str:
    if confidence < 0.75:
        return "needs_review"
    return "needs_review" if has_review_risk(warnings) else "published"
