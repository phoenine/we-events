from __future__ import annotations

import json
import os
from typing import Any

import requests

from core.activities.extraction_output import ActivityExtractionOutput, parse_activity_output
from core.common.log import logger


PROMPT_VERSION = "activity_extraction.v2"

MAX_MARKDOWN_CHARS = int(os.getenv("LLM_INPUT_MARKDOWN_CHARS", "60000"))
MAX_TEXT_CHARS = int(os.getenv("LLM_INPUT_TEXT_CHARS", "20000"))
MAX_IMAGE_COUNT = int(os.getenv("LLM_INPUT_IMAGE_COUNT", "24"))
MAX_IMAGE_CONTEXT_CHARS = int(os.getenv("LLM_INPUT_IMAGE_CONTEXT_CHARS", "160"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n[内容已截断，原始长度 {len(text)} 字符]"


def _compact_input_snapshot(input_snapshot: dict[str, Any]) -> dict[str, Any]:
    content = input_snapshot.get("content") or {}
    images = input_snapshot.get("images") or []
    compact_images = []
    for image in images[:MAX_IMAGE_COUNT]:
        compact_images.append(
            {
                "position": image.get("position"),
                "public_url": image.get("public_url") or "",
                "origin_url": image.get("origin_url") or "",
                "context_before": _truncate_text(
                    image.get("context_before"),
                    MAX_IMAGE_CONTEXT_CHARS,
                ),
                "context_after": _truncate_text(
                    image.get("context_after"),
                    MAX_IMAGE_CONTEXT_CHARS,
                ),
                "group_index": image.get("group_index"),
                "group_position": image.get("group_position"),
            }
        )

    return {
        "article": input_snapshot.get("article") or {},
        "content": {
            "markdown": _truncate_text(content.get("markdown"), MAX_MARKDOWN_CHARS),
            "text": _truncate_text(content.get("text"), MAX_TEXT_CHARS),
            "content_fetch_status": content.get("content_fetch_status") or "pending",
        },
        "images": compact_images,
        "options": input_snapshot.get("options") or {},
        "truncation": {
            "markdown_chars": MAX_MARKDOWN_CHARS,
            "text_chars": MAX_TEXT_CHARS,
            "image_count": MAX_IMAGE_COUNT,
            "image_context_chars": MAX_IMAGE_CONTEXT_CHARS,
            "original_image_count": len(images),
        },
    }


def _build_prompt(input_snapshot: dict[str, Any]) -> str:
    compact_snapshot = _compact_input_snapshot(input_snapshot)
    return (
        "你是一名微信公众号活动信息抽取助手。请根据输入中的文章正文和图片信息，"
        "判断文章是否包含活动信息，并只输出一个合法 JSON 对象。不要输出 markdown 代码块、解释或额外文字。\n\n"
        "输出 JSON 格式：\n"
        "{\n"
        '  "is_activity_article": true,\n'
        '  "confidence": 0.86,\n'
        '  "reason": "文章包含明确活动时间、地点和报名方式",\n'
        '  "activities": [\n'
        "    {\n"
        '      "title": "活动标题",\n'
        '      "summary": "活动摘要",\n'
        '      "event_time_text": "原文中的活动时间",\n'
        '      "start_at": "2026-06-10T19:00:00+08:00",\n'
        '      "end_at": "2026-06-10T21:00:00+08:00",\n'
        '      "location_text": "原文中的活动地点",\n'
        '      "registration_text": "原文中的报名说明",\n'
        '      "registration_method": "qr_code|link|phone|wechat|onsite|none|unknown",\n'
        '      "registration_url": "报名链接，没有则为空字符串",\n'
        '      "qr_image_urls": [],\n'
        '      "fee_text": "原文中的费用说明",\n'
        '      "audience": "目标人群",\n'
        '      "evidence": [{"field":"event_time","text":"证据原文","source":"text","image_urls":[]}],\n'
        '      "warnings": []\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "如果不是活动文章，输出：\n"
        '{"is_activity_article": false, "confidence": 0, "reason": "不是活动文章", "activities": []}\n\n'
        "规则：\n"
        "- 一篇文章可能包含多个活动。\n"
        "- article.publish_date 是文章在 Asia/Shanghai 时区的发布日期。\n"
        "- 即日起、即日、今日、当天等相对日期必须以 article.publish_date 为基准转换为具体日期，"
        "start_at/end_at 使用带 +08:00 时区的 ISO 8601 时间，event_time_text 也必须改写为具体日期。\n"
        "- 相对日期的原文必须保留在 evidence.text 中。\n"
        "- 时间无法规范化时，start_at/end_at 使用 null，但保留 event_time_text。\n"
        "- event_status 不要输出，后端会计算。\n"
        "- 只能使用给定证据，不要编造地点、时间、报名方式。\n\n"
        "输入快照：\n"
        f"{json.dumps(compact_snapshot, ensure_ascii=False)}"
    )


def extract_activities_with_llm(input_snapshot: dict[str, Any]) -> tuple[ActivityExtractionOutput, str, str]:
    api_base = os.getenv("LLM_API_BASE", "https://api.siliconflow.cn/v1/chat/completions")
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "Qwen/Qwen3-32B")

    if not api_key:
        raise RuntimeError("未配置 LLM_API_KEY，无法进行活动抽取")

    prompt = _build_prompt(input_snapshot)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "8192")),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    compact_input_size = len(json.dumps(_compact_input_snapshot(input_snapshot), ensure_ascii=False))
    logger.info(
        "[activities.extract] call llm "
        f"model={model} input_size={compact_input_size} timeout={LLM_TIMEOUT_SECONDS}"
    )
    try:
        response = requests.post(
            api_base,
            headers=headers,
            json=payload,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise RuntimeError(f"LLM 请求超时，已发送输入约 {compact_input_size} 字符") from exc
    except requests.HTTPError as exc:
        status_code = getattr(exc.response, "status_code", "unknown")
        body = getattr(exc.response, "text", "")[:300] if exc.response is not None else ""
        raise RuntimeError(f"LLM 请求失败，status={status_code}, body={body}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"LLM 请求异常: {exc.__class__.__name__}") from exc

    data = response.json()
    raw_text = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
    output = parse_activity_output(raw_text)
    return output, raw_text, model
