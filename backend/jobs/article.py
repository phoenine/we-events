from core.articles import article_repo
from core.common.app_settings import settings
from core.common.log import logger
from core.common.utils.async_tools import run_sync
from core.integrations.supabase.storage import supabase_storage_articles
from core.articles.content_format import format_content
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import mimetypes
import re
import requests
import uuid

ARTICLE_COLUMNS = {
    "id",
    "wechat_account_id",
    "title",
    "description",
    "pic_url",
    "content",
    "content_md",
    "content_fetch_status",
    "content_fetch_error",
    "activity_extraction_status",
    "activity_extraction_error",
    "publish_time",
    "url",
    "created_at",
    "updated_at",
}


def _normalize_epoch_seconds(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        epoch = int(float(value))
    except (TypeError, ValueError):
        return None
    # 微信列表接口和正文解析都应为秒级时间戳；这里兼容误传的毫秒。
    if epoch > 10_000_000_000:
        epoch = epoch // 1000
    return epoch if epoch > 0 else None


def _extract_object_path_from_storage_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    bucket = supabase_storage_articles.bucket
    public_prefix = f"/storage/v1/object/public/{bucket}/"
    sign_prefix = f"/storage/v1/object/sign/{bucket}/"
    if public_prefix in value:
        return value.split(public_prefix, 1)[1].split("?", 1)[0]
    if sign_prefix in value:
        return value.split(sign_prefix, 1)[1].split("?", 1)[0]
    if value.startswith("articles/"):
        return value.split("?", 1)[0]
    return ""


def _sanitize_slug(value: str, default: str = "article") -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-")
    return text[:80] or default


def _guess_filename(image_url: str, content_type: str, index: int) -> str:
    parsed = urlparse(image_url)
    name = parsed.path.rsplit("/", 1)[-1]
    if not name or "." not in name:
        ext = mimetypes.guess_extension(content_type or "") or ".jpg"
        name = f"image-{index}{ext}"
    return _sanitize_slug(name, f"image-{index}.jpg")


def _format_storage_path(template: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(values.get(key, values.get("uuid", str(uuid.uuid4()))))

    return re.sub(r"\{([a-zA-Z0-9_]+)\}", replace, template)


def _upload_article_images(article: dict) -> tuple[dict, list[dict]]:
    content = str(article.get("content") or "")
    if not content or not supabase_storage_articles.valid():
        return article, []

    soup = BeautifulSoup(content, "html.parser")
    images = soup.find_all("img")
    if not images:
        return article, []

    article_id = str(article.get("id") or str(uuid.uuid4()))
    article_name = _sanitize_slug(str(article.get("title") or article_id))
    mappings: list[dict] = []
    stat_total = 0
    stat_reuse_public_url = 0
    stat_reuse_existing_object = 0
    stat_uploaded = 0

    for i, img in enumerate(images, start=1):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        stat_total += 1
        try:
            # 已经是目标存储链接则跳过
            if f"/storage/v1/object/public/{supabase_storage_articles.bucket}/" in src:
                existing_path = _extract_object_path_from_storage_url(src)
                if existing_path:
                    mappings.append(
                        {
                            "bucket": supabase_storage_articles.bucket,
                            "object_path": existing_path,
                            "public_url": supabase_storage_articles.public_url(
                                existing_path
                            ),
                            "origin_url": src,
                            "position": i,
                        }
                    )
                    stat_reuse_public_url += 1
                continue

            filename = _guess_filename(src, "", i)
            path = _format_storage_path(
                supabase_storage_articles.path,
                {
                    "uuid": str(uuid.uuid4()),
                    "article_id": article_id,
                    "article_name": article_name,
                    "filename": filename,
                },
            )
            # 目标已存在则直接复用，避免重复下载和上传
            exists = run_sync(supabase_storage_articles.exists(path))
            if not exists:
                resp = requests.get(src, timeout=15)
                resp.raise_for_status()
                ctype = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0]
                run_sync(
                    supabase_storage_articles.upload_bytes(
                        path=path,
                        data=resp.content,
                        content_type=ctype,
                    )
                )
                stat_uploaded += 1
            else:
                stat_reuse_existing_object += 1
            public_url = supabase_storage_articles.public_url(path)
            img["src"] = public_url
            if "data-src" in img.attrs:
                del img.attrs["data-src"]
            mappings.append(
                {
                    "bucket": supabase_storage_articles.bucket,
                    "object_path": path,
                    "public_url": public_url,
                    "origin_url": src,
                    "position": i,
                }
            )
        except Exception as e:
            logger.warning(f"文章图片上传失败，保留原链接: {e}")

    if stat_total > 0:
        logger.info(
            f"[dedup-debug] article_id={article_id} image_total={stat_total} "
            f"reuse_public={stat_reuse_public_url} reuse_existing_object={stat_reuse_existing_object} "
            f"uploaded={stat_uploaded}"
        )

    article["content"] = str(soup)
    return article, mappings


def _normalize_article_for_db(article: dict) -> dict:
    """将采集侧字段归一化到 articles 表字段。"""
    data = dict(article or {})

    publish_time = (
        _normalize_epoch_seconds(data.get("publish_time"))
        or _normalize_epoch_seconds(data.get("create_time"))
        or _normalize_epoch_seconds(data.get("update_time"))
    )
    if publish_time is not None:
        data["publish_time"] = publish_time

    # 表外字段（采集上下文）不入库
    data.pop("images", None)
    data.pop("mp_info", None)
    data.pop("ext", None)

    # 仅保留 articles 表已定义字段，避免 schema 漂移导致入库失败
    return {k: v for k, v in data.items() if k in ARTICLE_COLUMNS}


def _ensure_content_markdown(article: dict) -> dict:
    content = str(article.get("content") or "").strip()
    if not content:
        return article
    if str(article.get("content_md") or "").strip():
        return article
    try:
        article["content_md"] = format_content(content, "markdown")
    except Exception as e:
        logger.warning(f"生成 content_md 失败: {e}")
    return article


def UpdateArticle(art: dict, check_exist: bool = False):
    """更新文章"""
    if settings.debug:
        pass
    try:
        article_id = str((art or {}).get("id") or "")
        existing_article = None
        if article_id:
            rows = article_repo.sync_get_articles(filters={"id": article_id}, limit=1)
            existing_article = rows[0] if rows else None

        art, image_mappings = _upload_article_images(dict(art))
        art = _ensure_content_markdown(art)
        art["content_fetch_status"] = "fetched" if art.get("content") else "pending"
        if existing_article:
            art["activity_extraction_status"] = existing_article.get(
                "activity_extraction_status"
            ) or "pending"
            art["activity_extraction_error"] = existing_article.get(
                "activity_extraction_error"
            )
        else:
            art["activity_extraction_status"] = "pending"
        art = _normalize_article_for_db(art)
        # 使用 Supabase 创建文章
        result = article_repo.sync_create_article(art)
        if result:
            article_id = str(result.get("id") or art.get("id") or "")
            if article_id:
                try:
                    article_repo.sync_replace_article_images(article_id, image_mappings)
                except Exception as e:
                    logger.warning(f"写入 article_images 映射失败 article_id={article_id}: {e}")
            return True
    except Exception as e:
        logger.info(f"创建文章失败: {e}")
    return False


def Update_Over(data=None):
    logger.info("更新完成")
    pass
