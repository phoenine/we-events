from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import BaseModel


class OcrConfigurationError(RuntimeError):
    """Raised when the external OCR provider is not configured."""


class OcrResult(BaseModel):
    text: str = ""
    confidence: float | None = None
    provider: str = "openai-compatible"


def build_ocr_payload(model: str, image_url: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "请识别图片中所有可见文字，按自然阅读顺序输出纯文本。"
                            "不要解释、总结或使用 Markdown 代码块；没有文字时返回空字符串。"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                ],
            }
        ],
        "temperature": 0,
    }


def _message_text(data: dict[str, Any]) -> str:
    content = (data.get("choices", [{}])[0].get("message", {}) or {}).get(
        "content", ""
    )
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(item.get("text") or "").strip()
            for item in content
            if isinstance(item, dict)
        ]
        return "\n".join(part for part in parts if part)
    return ""


class OpenAICompatibleOcrClient:
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
    def from_environment(cls) -> "OpenAICompatibleOcrClient":
        api_base = os.getenv("OCR_API_BASE", "").strip()
        api_key = os.getenv("OCR_API_KEY", "").strip()
        model = os.getenv("OCR_MODEL", "").strip()
        if not api_base or not api_key or not model:
            raise OcrConfigurationError(
                "未配置 OCR_API_BASE、OCR_API_KEY 或 OCR_MODEL"
            )
        try:
            timeout_seconds = float(os.getenv("OCR_REQUEST_TIMEOUT_SECONDS", "60"))
        except ValueError:
            timeout_seconds = 60
        return cls(
            api_base=api_base,
            api_key=api_key,
            model=model,
            timeout_seconds=max(1, timeout_seconds),
        )

    async def recognize(self, image_url: str) -> OcrResult:
        if not str(image_url or "").strip():
            raise ValueError("图片 URL 为空")
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.api_base,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=build_ocr_payload(self.model, image_url),
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("OCR 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"OCR 请求失败，status={exc.response.status_code}") from exc
        except (httpx.RequestError, ValueError) as exc:
            raise RuntimeError(f"OCR 请求异常: {exc.__class__.__name__}") from exc

        text = _message_text(data)
        return OcrResult(text=text)
