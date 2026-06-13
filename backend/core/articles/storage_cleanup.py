from __future__ import annotations

import re
from typing import Any

from core.articles import article_repo
from core.common.log import logger
from core.common.utils.async_tools import run_sync
from core.integrations.supabase.storage import supabase_storage_articles


def extract_storage_paths_from_content(content: str) -> list[str]:
    html = str(content or "")
    if not html:
        return []
    bucket = supabase_storage_articles.bucket
    public_prefix = f"/storage/v1/object/public/{bucket}/"
    sign_prefix = f"/storage/v1/object/sign/{bucket}/"
    paths: set[str] = set()

    for src in re.findall(r"""(?:src|data-src)\s*=\s*["']([^"']+)["']""", html):
        value = (src or "").strip()
        if not value:
            continue
        if public_prefix in value:
            paths.add(value.split(public_prefix, 1)[1].split("?", 1)[0])
            continue
        if sign_prefix in value:
            paths.add(value.split(sign_prefix, 1)[1].split("?", 1)[0])
            continue
        if value.startswith("articles/"):
            paths.add(value.split("?", 1)[0])
    return [path for path in paths if path]


async def delete_article_storage_objects(article: dict[str, Any]) -> int:
    article_id = str(article.get("id") or "")
    paths: set[str] = set()

    if article_id:
        try:
            mapped_rows = await article_repo.get_article_images(article_id)
            for row in mapped_rows:
                path = str(row.get("object_path") or "").strip()
                if path:
                    paths.add(path)
        except Exception as exc:
            logger.warning(f"读取文章图片映射失败 article_id={article_id}: {exc}")

    if not paths:
        for path in extract_storage_paths_from_content(str(article.get("content") or "")):
            paths.add(path)

    deleted = 0
    for path in paths:
        ok = await supabase_storage_articles.delete_object(path)
        if ok:
            deleted += 1
    return deleted


def delete_article_storage_objects_sync(article: dict[str, Any]) -> int:
    return run_sync(delete_article_storage_objects(article))
