from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from core.common.utils.async_tools import run_sync


class ArticleRepository:

    ARTICLE_TABLE = "articles"
    ARTICLE_IMAGE_TABLE = "article_images"

    def __init__(self, client: Any):
        self.client = client

    async def get_articles_base(
        self,
        filters: Optional[Dict] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: str = "publish_time.desc",
    ):
        """获取文章列表"""
        return await self.client.select(
            self.ARTICLE_TABLE,
            filters=filters,
            limit=limit,
            offset=offset,
            order=order_by,
        )

    async def get_articles(
        self,
        wechat_account_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: str = "publish_time.desc",
    ):
        """根据公众号ID获取文章列表"""
        filters = {}
        if wechat_account_id is not None:
            filters["wechat_account_id"] = wechat_account_id

        return await self.client.select(
            self.ARTICLE_TABLE,
            filters=filters or None,
            limit=limit,
            offset=offset,
            order=order_by,
        )

    async def get_articles_by_wechat_account_ids(
        self,
        wechat_account_ids: List[str],
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ):
        """根据公众号账号 ID 列表获取文章"""
        return await self.client.select(
            self.ARTICLE_TABLE,
            filters={"wechat_account_id": {"in": wechat_account_ids}},
            limit=limit,
            offset=offset,
            order="publish_time.desc",
        )

    async def get_articles_by_id(
        self,
        article_id: str,
    ):
        """根据文章ID获取文章"""
        return await self.client.select(
            self.ARTICLE_TABLE, filters={"id": article_id}, limit=1
        )

    async def get_articles_by_time_range(
        self, start_time: datetime, end_time: datetime, limit: Optional[int] = None
    ):
        filters = {
            "publish_time": {
                "gte": int(start_time.timestamp()),
                "lte": int(end_time.timestamp()),
            }
        }
        return await self.client.select(
            self.ARTICLE_TABLE, filters=filters, order="publish_time.desc", limit=limit
        )

    async def count_articles_base(self, filters: Optional[Dict] = None):
        """统计文章数量"""
        return await self.client.count(self.ARTICLE_TABLE, filters=filters)

    async def count_articles(self, wechat_account_id=None):
        """统计文章数量"""
        filters = {}
        if wechat_account_id is not None:
            filters["wechat_account_id"] = wechat_account_id
        return await self.client.count(self.ARTICLE_TABLE, filters=filters)

    async def search_articles(self, keyword: str, limit: int = 100):
        """搜索文章"""
        # 格式化搜索关键词
        words = keyword.replace("-", " ").replace("|", " ").split(" ")
        words = [word.strip() for word in words if word.strip()]
        if not words:
            return []

        # 构建OR条件搜索
        filters = {"or": []}
        for word in words:
            filters["or"].append({"title": {"like": f"%{word}%"}})

        return await self.client.select(
            self.ARTICLE_TABLE, filters=filters, limit=limit, order="publish_time.desc"
        )

    # TODO: 统一文章列表查询接口, 支持 search + 过滤条件
    # async def list_articles(
    #     self,
    #     wechat_account_id: Optional[str] = None,
    #     status: Optional[int] = None,
    #     search: Optional[str] = None,
    #     limit: Optional[int] = None,
    #     offset: Optional[int] = None,
    #     order_by: str = "publish_at.desc",
    # ) -> tuple[list[dict[str, Any]], int]:
    #     """
    #     统一的文章列表查询：
    #     - 支持按 wechat_account_id + status 过滤
    #     - 支持搜索（search 一旦有值，将忽略 wechat_account_id/status 过滤，与当前 API 行为保持一致）
    #     - 返回 (articles, total)
    #     """
    #     if search:
    #         # 搜索模式：沿用原先 search_articles 的语义
    #         if limit is not None and offset is not None:
    #             raw = await self.search_articles(search, limit=limit + offset)
    #             total = len(raw)
    #             articles = raw[offset : offset + limit]
    #         else:
    #             raw = await self.search_articles(search)
    #             total = len(raw)
    #             articles = raw
    #         return articles, total
    #
    #     # 非搜索模式：按 wechat_account_id + status 过滤
    #     filters: dict[str, Any] = {}
    #     if wechat_account_id is not None:
    #         filters["wechat_account_id"] = wechat_account_id
    #     if status is not None:
    #         filters["status"] = status
    #
    #     articles = await self.client.select(
    #         self.ARTICLE_TABLE,
    #         filters=filters or None,
    #         limit=limit,
    #         offset=offset,
    #         order=order_by,
    #     )
    #     total = await self.count_articles(wechat_account_id=wechat_account_id, status=status)
    #     return articles, total

    async def clean_expired_articles(self, days: int = 15):
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_ts = int(cutoff_date.timestamp())
        expired_articles = await self.client.select(
            self.ARTICLE_TABLE,
            filters={"publish_time": {"lt": cutoff_ts}},
        )

        if not expired_articles:
            return 0

        article_ids = [article["id"] for article in expired_articles]
        deleted_articles = await self.client.delete(
            self.ARTICLE_TABLE, {"id": {"in": article_ids}}
        )
        return len(deleted_articles)

    async def delete_article(self, article_id: str):
        """删除文章"""
        return await self.client.delete(self.ARTICLE_TABLE, {"id": article_id})

    async def get_article_images(self, article_id: str):
        """获取文章关联图片映射。"""
        return await self.client.select(
            self.ARTICLE_IMAGE_TABLE,
            filters={"article_id": article_id},
            order="position.asc,created_at.asc",
        )

    async def delete_article_images_by_article(self, article_id: str):
        """删除文章关联图片映射。"""
        return await self.client.delete(
            self.ARTICLE_IMAGE_TABLE, {"article_id": article_id}
        )

    async def delete_article_images_by_articles(self, article_ids: List[str]):
        """批量删除多篇文章图片映射。"""
        if not article_ids:
            return []
        return await self.client.delete(
            self.ARTICLE_IMAGE_TABLE, {"article_id": {"in": article_ids}}
        )

    async def replace_article_images(self, article_id: str, images: List[Dict[str, Any]]):
        """按文章替换图片映射（先删后插，确保与最新正文一致）。"""
        await self.delete_article_images_by_article(article_id)
        rows: List[Dict[str, Any]] = []
        for idx, img in enumerate(images, start=1):
            object_path = str(img.get("object_path") or "").strip()
            if not object_path:
                continue
            rows.append(
                {
                    "article_id": article_id,
                    "bucket": img.get("bucket") or "article-images",
                    "object_path": object_path,
                    "public_url": img.get("public_url") or "",
                    "origin_url": img.get("origin_url") or "",
                    "position": img.get("position") or idx,
                }
            )
        if not rows:
            return []
        return await self.client.upsert(
            self.ARTICLE_IMAGE_TABLE,
            rows,
            on_conflict="article_id,object_path",
        )

    async def create_article(self, article_data: Dict):
        """创建文章（按 id 幂等写入：存在则更新，不存在则插入）"""
        rows = await self.client.upsert(
            self.ARTICLE_TABLE,
            article_data,
            on_conflict="id",
        )
        return rows[0] if rows else {}

    async def update_article(self, article_id: str, article_data: Dict):
        """更新文章"""
        article_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.client.update(
            self.ARTICLE_TABLE, article_data, filters={"id": article_id}
        )

    #! 同步接口封装，用于jobs

    def sync_create_article(self, article_data: Dict):
        """同步创建文章（用于兼容同步代码）"""
        return run_sync(self.create_article(article_data))

    def sync_update_article(self, article_id: str, article_data: Dict):
        """同步更新文章（用于兼容同步代码）"""
        return run_sync(self.update_article(article_id, article_data))

    def sync_count_articles(self, filters: Optional[Dict] = None):
        """同步统计文章数量（用于兼容同步代码）"""
        return run_sync(self.count_articles_base(filters=filters))

    def sync_get_articles(
        self,
        filters: Optional[Dict] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: str = "publish_time.desc",
    ):
        """同步获取文章列表（用于兼容同步代码）"""
        return run_sync(
            self.get_articles_base(
                filters=filters, limit=limit, offset=offset, order_by=order_by
            )
        )

    def sync_delete_article(self, article_id: str):
        """同步删除文章（用于兼容同步代码）"""
        return run_sync(self.delete_article(article_id))

    def sync_replace_article_images(self, article_id: str, images: List[Dict[str, Any]]):
        """同步替换文章图片映射（用于兼容同步代码）。"""
        return run_sync(self.replace_article_images(article_id, images))
