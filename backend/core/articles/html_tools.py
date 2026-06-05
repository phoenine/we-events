from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from core.common.log import logger

SelectorItem = str | tuple[str, str] | dict[str, Any]

MEDIA_TAGS = {
    "audio",
    "canvas",
    "embed",
    "iframe",
    "img",
    "object",
    "picture",
    "source",
    "svg",
    "track",
    "video",
}
NON_CONTENT_TAGS = {"head", "link", "meta", "noscript", "script", "style"}
ATTR_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_:-]*$")


def clean_html(
    html_content: str,
    remove_ids: Sequence[str] | None = None,
    remove_classes: Sequence[str] | None = None,
    remove_selectors: Sequence[str] | None = None,
    remove_xpaths: Sequence[str] | None = None,
    remove_attributes: Sequence[dict[str, Any]] | None = None,
) -> str:
    """清理文章 HTML 内容，移除指定元素、属性匹配元素和空文本元素。"""
    if not html_content:
        return html_content

    selectors = _build_selectors(
        remove_ids=remove_ids,
        remove_classes=remove_classes,
        remove_selectors=remove_selectors,
        remove_xpaths=remove_xpaths,
    )

    try:
        soup = BeautifulSoup(html_content, "html.parser")
        removed_count = 0
        removed_count += _remove_by_selectors(soup, selectors)
        removed_count += _remove_by_attributes(soup, remove_attributes or ())
        removed_count += _remove_empty_text_elements(soup)
        if removed_count > 0:
            logger.info(f"HTML 清理完成，共移除 {removed_count} 个元素")
        return str(soup)
    except Exception as e:
        logger.error(f"HTML 清理失败: {e}")
        return html_content


def remove_elements_by_attributes(
    html_content: str,
    attributes: Sequence[dict[str, Any]],
) -> str:
    """根据属性移除 HTML 元素。"""
    if not html_content or not attributes:
        return html_content
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        removed_count = _remove_by_attributes(soup, attributes)
        if removed_count > 0:
            logger.info(f"根据属性成功移除 {removed_count} 个 HTML 元素")
        return str(soup)
    except Exception as e:
        logger.error(f"根据属性移除元素失败: {e}")
        return html_content


def remove_empty_text_elements(html_content: str) -> str:
    """移除空文本元素，同时保留图片、视频等媒体容器。"""
    if not html_content:
        return html_content
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        removed_count = _remove_empty_text_elements(soup)
        if removed_count > 0:
            logger.info(f"成功移除 {removed_count} 个空文本元素")
        return str(soup)
    except Exception as e:
        logger.error(f"移除空文本元素失败: {e}")
        return html_content


def remove_html_elements(
    html_content: str,
    selectors: Sequence[SelectorItem],
) -> str:
    """从 HTML 中移除指定元素。

    selectors 支持：
    - 字符串：默认按 id 查找
    - tuple: `(selector, type)`
    - dict: `{"selector": "...", "type": "css|xpath|id|class"}`
    """
    if not html_content or not selectors:
        return html_content
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        removed_count = _remove_by_selectors(soup, selectors)
        if removed_count > 0:
            logger.info(f"成功移除 {removed_count} 个 HTML 元素")
        return str(soup)
    except Exception as e:
        logger.error(f"HTML 元素移除失败: {e}")
        return html_content


def normalize_html(html_string: str) -> str:
    """标准化 HTML 字符串用于比较。"""
    normalized = re.sub(r"\s+", " ", html_string or "")
    return normalized.strip()


def _build_selectors(
    *,
    remove_ids: Sequence[str] | None,
    remove_classes: Sequence[str] | None,
    remove_selectors: Sequence[str] | None,
    remove_xpaths: Sequence[str] | None,
) -> list[dict[str, str]]:
    selectors: list[dict[str, str]] = []
    selectors.extend({"selector": value, "type": "id"} for value in remove_ids or ())
    selectors.extend(
        {"selector": value, "type": "class"} for value in remove_classes or ()
    )
    selectors.extend(
        {"selector": value, "type": "css"} for value in remove_selectors or ()
    )
    selectors.extend(
        {"selector": value, "type": "xpath"} for value in remove_xpaths or ()
    )
    return selectors


def _parse_selector(selector_item: SelectorItem) -> tuple[str, str]:
    if isinstance(selector_item, dict):
        return (
            str(selector_item.get("selector") or "").strip(),
            str(selector_item.get("type") or "id").strip().lower(),
        )
    if isinstance(selector_item, tuple) and len(selector_item) >= 2:
        return str(selector_item[0]).strip(), str(selector_item[1]).strip().lower()
    return str(selector_item).strip(), "id"


def _remove_by_selectors(
    soup: BeautifulSoup,
    selectors: Sequence[SelectorItem],
) -> int:
    removed_count = 0
    for selector_item in selectors:
        selector, selector_type = _parse_selector(selector_item)
        if not selector:
            continue

        try:
            if selector_type == "xpath":
                removed_count += _remove_by_xpath(soup, selector)
                continue
            elements = _find_by_selector(soup, selector, selector_type)
            removed_count += _decompose(elements)
        except Exception as e:
            logger.error(
                f"移除元素失败 (选择器: {selector}, 类型: {selector_type}): {e}"
            )
    return removed_count


def _find_by_selector(
    soup: BeautifulSoup,
    selector: str,
    selector_type: str,
) -> list[Tag]:
    if selector_type == "css":
        return [
            element for element in soup.select(selector) if isinstance(element, Tag)
        ]
    if selector_type == "id":
        return [
            element
            for element in soup.find_all(id=selector)
            if isinstance(element, Tag)
        ]
    if selector_type == "class":
        return [
            element
            for element in soup.find_all(class_=selector)
            if isinstance(element, Tag)
        ]
    logger.warning(f"不支持的选择器类型: {selector_type}")
    return []


def _remove_by_xpath(soup: BeautifulSoup, selector: str) -> int:
    try:
        from lxml import html
    except ImportError:
        logger.warning("lxml 未安装，无法使用 xpath 选择器")
        return 0

    try:
        lxml_tree = html.fromstring(str(soup))
        elements = lxml_tree.xpath(selector)
        removed_count = 0
        for element in elements:
            parent = element.getparent() if hasattr(element, "getparent") else None
            if parent is not None:
                parent.remove(element)
                removed_count += 1

        if removed_count:
            replacement = BeautifulSoup(
                html.tostring(lxml_tree, encoding="unicode", pretty_print=False),
                "html.parser",
            )
            soup.clear()
            for child in list(replacement.contents):
                soup.append(child)
        return removed_count
    except Exception as e:
        logger.error(f"XPath 处理失败: {e}")
        return 0


def _remove_by_attributes(
    soup: BeautifulSoup,
    attributes: Sequence[dict[str, Any]],
) -> int:
    removed_count = 0
    for attr_config in attributes:

        attr_name = str(attr_config.get("name") or "").strip()
        attr_value = attr_config.get("value")
        exact_match = bool(attr_config.get("eq"))
        if not attr_name or not ATTR_NAME_RE.match(attr_name):
            logger.warning(f"跳过非法 HTML 属性名: {attr_name}")
            continue

        elements = _find_by_attribute(soup, attr_name, attr_value, exact_match)
        removed_count += _decompose(elements)
    return removed_count


def _find_by_attribute(
    soup: BeautifulSoup,
    attr_name: str,
    attr_value: Any,
    exact_match: bool,
) -> list[Tag]:
    if attr_value is None or attr_value == "":
        return [
            element
            for element in soup.find_all(attrs={attr_name: True})
            if isinstance(element, Tag)
        ]

    expected = str(attr_value)
    if exact_match:
        return [
            element
            for element in soup.find_all(attrs={attr_name: expected})
            if isinstance(element, Tag)
        ]

    matches: list[Tag] = []
    for element in soup.find_all(attrs={attr_name: True}):
        if not isinstance(element, Tag):
            continue
        actual = element.get(attr_name)
        values = actual if isinstance(actual, list) else [actual]
        if any(expected in str(value) for value in values if value is not None):
            matches.append(element)
    return matches


def _remove_empty_text_elements(soup: BeautifulSoup) -> int:
    removed_count = 0
    # 自底向上处理，避免父节点先删除导致子节点状态失真。
    for element in reversed(list(soup.find_all())):
        if not isinstance(element, Tag):
            continue
        if element.name in MEDIA_TAGS or element.name in NON_CONTENT_TAGS:
            continue
        if _has_visible_content(element):
            continue
        element.decompose()
        removed_count += 1
    return removed_count


def _has_visible_content(element: Tag) -> bool:
    if element.get_text(strip=True):
        return True
    return any(
        isinstance(child, Tag) and child.name in MEDIA_TAGS
        for child in element.descendants
    )


def _decompose(elements: Iterable[Tag]) -> int:
    removed_count = 0
    seen: set[int] = set()
    for element in elements:
        if not isinstance(element, Tag):
            continue
        element_id = id(element)
        if element_id in seen:
            continue
        seen.add(element_id)
        if element.parent is None:
            continue
        element.decompose()
        removed_count += 1
    return removed_count
