import json
import os
import re
from typing import Optional, Dict, Any

import requests

from core.common.log import logger


def analyze_article_for_activity(
    title: str, content: Optional[str], default_url: Optional[str]
) -> Dict[str, Any]:
    api_base = os.getenv(
        "LLM_API_BASE", "https://api.siliconflow.cn/v1/chat/completions"
    )
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "Qwen/Qwen3-32B")

    full_text = f"标题：{title or ''}\n正文: {content or ''}".strip()

    logger.debug(
        "[activities.llm] input "
        f"title_len={len(title or '')}, content_len={len(content or '')}, "
        f"default_url_present={bool(default_url)}"
    )
    logger.info(
        "[activities.llm] setup "
        f"api_base={api_base}, model={model}, key_present={bool(api_key)}"
    )

    if not api_key:
        logger.warning("[activities.llm] LLM_API_KEY missing, using heuristic fallback")
        logger.debug(f"[activities.llm] heuristic_text_sample={full_text[:200]!r}")
        is_event = any(
            k in full_text
            for k in [
                "活动",
                "讲座",
                "分享会",
                "沙龙",
                "大会",
                "培训",
                "路演",
                "赛",
                "招募",
                "报名",
            ]
        )
        if not is_event:
            logger.info("[activities.llm] heuristic says not an activity")
            return {"is_event": False}
        ret = {
            "is_event": True,
            "registration_time": "即时",
            "registration_method": default_url,
            "event_time": "未知",
            "event_fee": "未知",
            "audience": "未知",
            "registration_title": "无",
        }
        logger.debug(f"[activities.llm] heuristic_result={ret}")
        return ret

    prompt = (
        "你是一名结构化信息抽取助手。请根据以下微信公众号文章的标题与正文，"
        "判断该文章是否与【线上或线下活动】相关（例如讲座、培训、沙龙、招募、比赛、展览、分享会等）。"
        '如果不是活动，请输出：{"is_event": false}。\n\n'
        "如果是活动，请严格按照以下字段定义提取并返回 JSON 对象（不要包含额外说明或文字）：\n\n"
        "字段定义：\n"
        "1. is_event（布尔）— 是否为活动类文章。\n"
        "2. registration_title（字符串）— 活动的标题或主题。如果文章中有明确活动名或标题，请提取并总结为20字以内。\n"
        "3. registration_time（字符串）— 报名时间；若未提及，填“即刻报名”。\n"
        "4. registration_method（字符串）— 报名方式（例如链接、二维码、公众号回复等）；若未提及，填“参考公众号文章内容”。\n"
        "5. event_time（字符串）— 活动举行的具体时间；若未提及，填“未知”。\n"
        "6. event_fee（字符串）— 活动费用说明，如“免费”“99元/人”；若未提及，填“未知”。\n"
        "7. audience（字符串）— 目标参与人群，例如“亲子”“青少年”“公众”“高校学生”；若未提及，填“未知”。\n\n"
        "注意：请仅输出一个合法的 JSON 对象，不要添加任何自然语言解释或多余文字。\n\n"
        f"以下为文章内容：\n标题：{title or ''}\n正文：{content or ''}\n\n"
        "请开始输出。"
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        payload_size = len(json.dumps(payload, ensure_ascii=False))
    except Exception:
        payload_size = -1
    logger.debug(
        "[activities.llm] request "
        f"payload_size={payload_size}, prompt_len={len(prompt)}, timeout=30"
    )

    try:
        resp = requests.post(api_base, headers=headers, json=payload, timeout=600)
        logger.debug(
            "[activities.llm] response "
            f"status={resp.status_code}, elapsed={getattr(resp, 'elapsed', None)}"
        )
        resp.raise_for_status()

        data = resp.json()
        logger.debug(f"[activities.llm] resp_json_keys={list(data.keys())}")

        content_text = (data.get("choices", [{}])[0].get("message", {}) or {}).get(
            "content", ""
        )
        logger.debug(f"[activities.llm] raw_content_sample={content_text[:300]!r}")

        m = re.search(r"\{.*\}", content_text, re.S)
        json_str = m.group(0) if m else content_text
        logger.debug(f"[activities.llm] extracted_json_sample={json_str[:300]!r}")

        result = json.loads(json_str)
        logger.debug(f"[activities.llm] parsed_result_keys={list(result.keys())}")

        is_event_raw = result.get("is_event", False)
        if isinstance(is_event_raw, str):
            is_event = is_event_raw.strip().lower() in [
                "true",
                "yes",
                "是",
                "活动",
                "y",
            ]
        else:
            is_event = bool(is_event_raw)

        logger.info(f"[activities.llm] is_event={is_event}")
        if not is_event:
            return {"is_event": False}

        registration_time = result.get("registration_time") or "即时"
        registration_method = result.get("registration_method") or (default_url or "无")
        event_time = result.get("event_time") or "无"
        event_fee = result.get("event_fee") or "无"
        audience = result.get("audience") or "无"
        registration_title = result.get("registration_title") or "无"

        ret = {
            "is_event": True,
            "registration_time": registration_time,
            "registration_method": registration_method,
            "event_time": event_time,
            "event_fee": event_fee,
            "audience": audience,
            "registration_title": registration_title,
        }
        logger.debug(f"[activities.llm] normalized_result={ret}")
        return ret

    except requests.HTTPError as e:
        body = None
        try:
            body = resp.text[:500]
        except Exception:
            pass
        logger.exception(f"[activities.llm] HTTPError: {e}; body_sample={body!r}")
    except Exception as e:
        logger.exception(f"[activities.llm] analyze failed: {e}")

    is_event = any(
        k in full_text
        for k in [
            "活动",
            "讲座",
            "分享会",
            "沙龙",
            "大会",
            "培训",
            "路演",
            "赛",
            "招募",
            "报名",
        ]
    )
    if not is_event:
        logger.info("[activities.llm] fallback says not an activity")
        return {"is_event": False}
    ret = {
        "is_event": True,
        "registration_time": "即时",
        "registration_method": default_url or "无",
        "event_time": "无",
        "event_fee": "无",
        "audience": "无",
        "registration_title": "无",
    }
    logger.debug(f"[activities.llm] fallback_result={ret}")
    return ret
