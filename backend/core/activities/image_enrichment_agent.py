from __future__ import annotations

import json
import os
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from core.activities.extraction_output import extract_json_object


class ImageEnrichmentConfigurationError(RuntimeError):
    """Raised when the LLM used for enrichment is not configured."""


class ImageEnrichmentSuggestions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_time_text: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    location_text: str | None = None
    registration_text: str | None = None
    registration_method: str | None = None
    registration_url: str | None = None
    fee_text: str | None = None
    audience: str | None = None


class ImageEnrichmentOutput(BaseModel):
    suggestions: ImageEnrichmentSuggestions = Field(
        default_factory=ImageEnrichmentSuggestions
    )
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def parse_image_enrichment_output(text: str) -> dict[str, Any]:
    output = ImageEnrichmentOutput.model_validate(extract_json_object(text))
    return {
        "suggestions": output.suggestions.model_dump(exclude_none=True),
        "evidence": output.evidence,
        "warnings": output.warnings,
    }


def build_image_enrichment_prompt(
    *,
    activity: dict[str, Any],
    article: dict[str, Any],
    images: list[dict[str, Any]],
    missing_fields: list[str],
) -> str:
    snapshot = {
        "activity": activity,
        "missing_fields": missing_fields,
        "article": {
            "id": article.get("id"),
            "title": article.get("title") or "",
            "description": article.get("description") or "",
            "content": article.get("content_md") or article.get("content") or "",
        },
        "images": images,
    }
    return (
        "你是活动信息补全助手。根据当前活动、文章正文和图片 OCR 文本，"
        "只补充有明确证据支持的缺失字段。不要修改 article_id、活动 ID 或已有事实。"
        "只输出合法 JSON，结构为："
        '{"suggestions":{"event_time_text":null,"start_at":null,"end_at":null,'
        '"location_text":null,"registration_text":null,"registration_method":null,'
        '"registration_url":null,"fee_text":null,"audience":null},'
        '"evidence":[{"field":"location_text","text":"证据原文",'
        '"source":"image_ocr","image_ids":["图片ID"]}],"warnings":[]}。'
        "无法确认的字段使用 null，不要编造。输入："
        f"{json.dumps(snapshot, ensure_ascii=False, default=str)}"
    )


class OpenAICompatibleImageEnrichmentClient:
    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60,
    ) -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "OpenAICompatibleImageEnrichmentClient":
        api_base = os.getenv(
            "LLM_API_BASE", "https://api.siliconflow.cn/v1/chat/completions"
        ).strip()
        api_key = os.getenv("LLM_API_KEY", "").strip()
        model = os.getenv("LLM_MODEL", "Qwen/Qwen3-32B").strip()
        if not api_key:
            raise ImageEnrichmentConfigurationError(
                "未配置 LLM_API_KEY，无法生成图片补充建议"
            )
        try:
            timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
        except ValueError:
            timeout_seconds = 60
        return cls(
            api_base=api_base,
            api_key=api_key,
            model=model,
            timeout_seconds=max(1, timeout_seconds),
        )

    async def suggest(
        self,
        *,
        activity: dict[str, Any],
        article: dict[str, Any],
        images: list[dict[str, Any]],
        missing_fields: list[str],
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": build_image_enrichment_prompt(
                        activity=activity,
                        article=article,
                        images=images,
                        missing_fields=missing_fields,
                    ),
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.api_base,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("活动图片补充 LLM 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"活动图片补充 LLM 请求失败，status={exc.response.status_code}"
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise RuntimeError(
                f"活动图片补充 LLM 请求异常: {exc.__class__.__name__}"
            ) from exc

        raw_text = (data.get("choices", [{}])[0].get("message", {}) or {}).get(
            "content", ""
        )
        return parse_image_enrichment_output(str(raw_text or ""))
