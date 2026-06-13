from __future__ import annotations

from enum import Enum
import re
from typing import Any

from bs4 import BeautifulSoup


class ArticleContentQuality(str, Enum):
    FETCHED = "fetched"
    IMAGE_ONLY = "image_only"
    EMPTY = "empty"
    INACCESSIBLE = "inaccessible"


INACCESSIBLE_MARKERS = (
    "DELETED",
    "该内容已被发布者删除",
    "The content has been deleted by the author.",
    "内容审核中",
    "该内容暂时无法查看",
    "违规无法查看",
    "发送失败无法查看",
    "Unable to view this content because it violates regulation",
)

EMPTY_PLACEHOLDERS = {
    "",
    "暂无正文",
    "无正文",
}

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def _plain_text(value: str) -> str:
    html = str(value or "")
    if not html:
        return ""
    try:
        text = BeautifulSoup(html, "html.parser").get_text("", strip=True)
    except Exception:
        text = html.strip()
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[[^\]]*\]\([^)]+\)", "", text)
    text = URL_RE.sub("", text)
    return text.strip()


def _has_html_image(value: str) -> bool:
    html = str(value or "")
    if not html:
        return False
    try:
        return bool(BeautifulSoup(html, "html.parser").find("img"))
    except Exception:
        return "<img" in html.lower()


def _article_image_count(article: dict[str, Any], image_count: int | None) -> int:
    if image_count is not None:
        return max(0, int(image_count))
    images = article.get("images")
    if isinstance(images, list):
        return len([item for item in images if item])
    if _has_html_image(str(article.get("content") or "")):
        return 1
    return 0


def classify_article_content(
    article: dict[str, Any],
    *,
    image_count: int | None = None,
) -> ArticleContentQuality:
    content = str(article.get("content") or "")
    markdown = str(article.get("content_md") or "")
    combined = f"{content}\n{markdown}"
    if any(marker in combined for marker in INACCESSIBLE_MARKERS):
        return ArticleContentQuality.INACCESSIBLE

    text = _plain_text(markdown) or _plain_text(content)
    if text.strip() and text.strip() not in EMPTY_PLACEHOLDERS:
        return ArticleContentQuality.FETCHED

    if _article_image_count(article, image_count) > 0:
        return ArticleContentQuality.IMAGE_ONLY
    return ArticleContentQuality.EMPTY


def content_fetch_status_for_quality(quality: ArticleContentQuality) -> str:
    if quality == ArticleContentQuality.FETCHED:
        return "fetched"
    if quality == ArticleContentQuality.IMAGE_ONLY:
        return "fallback_required"
    return "failed"


def content_fetch_error_for_quality(quality: ArticleContentQuality) -> str:
    if quality == ArticleContentQuality.IMAGE_ONLY:
        return "文章正文为空，但包含图片，需走图片/截图兜底"
    if quality == ArticleContentQuality.EMPTY:
        return "文章正文为空，且未发现可用图片"
    if quality == ArticleContentQuality.INACCESSIBLE:
        return "微信文章不可访问或已删除"
    return ""


def build_content_quality_update(
    article: dict[str, Any],
    *,
    image_count: int | None = None,
) -> dict[str, str]:
    quality = classify_article_content(article, image_count=image_count)
    return {
        "content_fetch_status": content_fetch_status_for_quality(quality),
        "content_fetch_error": content_fetch_error_for_quality(quality),
    }
