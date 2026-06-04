from typing import Literal, cast
from bs4 import BeautifulSoup, Tag
import re
from markdownify import markdownify as md
from core.common.log import logger

# markdown 分支：需要 unwrap 的公众号分组（只保留内容）
TAGS_TO_UNWRAP = ["span", "font", "div", "strong", "b"]
# markdown 分支：需要从所有公众号分组上移除的属性
ATTRS_TO_STRIP = frozenset({"style", "class", "data-pm-slice", "data-title"})


def format_content(
    content: str,
    content_format: Literal["text", "markdown", "html"] = "html",
) -> str:
    """将 HTML 内容格式化为纯文本、Markdown 或保留 HTML。

    - text:  strip 所有公众号分组，保留纯文本，合并多余空行。
    - markdown: 去掉部分内联公众号分组、清理属性后，用 markdownify 转成 Markdown。
    - html: 原样返回。
    """
    try:
        if content_format == "text":
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text().strip()
            return re.sub(r"\n\s*\n", "\n", text)
        if content_format == "html":
            return content

        # markdown
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup.find_all(TAGS_TO_UNWRAP):
            cast(Tag, tag).unwrap()
        for t in soup.find_all(True):
            tag = cast(Tag, t)
            for attr in list(tag.attrs):
                if attr in ATTRS_TO_STRIP:
                    del tag.attrs[attr]

        content = str(soup)
        content = re.sub(
            r"(<p[^>]*>)([\s\S]*?)(<\/p>)",
            lambda m: m.group(1) + re.sub(r"\n", "", m.group(2)) + m.group(3),
            content,
        )
        content = re.sub(r"\n\s*\n\s*\n+", "\n", content)
        content = re.sub(r"\*", "", content)

        soup = BeautifulSoup(content, "html.parser")
        for img in soup.find_all("img"):
            img_tag = cast(Tag, img)
            if "title" in img_tag.attrs:
                img_tag["alt"] = img_tag["title"]
        content = str(soup)
        content = md(
            content, heading_style="ATX", bullets="-*+", code_language="python"
        )
        return re.sub(r"\n\s*\n\s*\n+", "\n\n", content)

    except Exception as e:
        logger.error(f"format_content error: {e}")
        return content
