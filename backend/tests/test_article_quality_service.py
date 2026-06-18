import unittest
from unittest.mock import patch

from core.articles.quality_service import reclassify_article_content_statuses


class FakeArticleRepo:
    def __init__(self):
        self.articles = [
            {"id": "empty", "content": "暂无正文", "content_md": "", "url": "https://example.com/empty"},
            {"id": "image", "content": "", "content_md": "", "url": "https://example.com/image"},
            {"id": "gone", "content": "该内容已被发布者删除", "content_md": ""},
        ]
        self.updated = []

    async def get_articles_base(self, filters=None, limit=None, offset=None, order_by="publish_time.desc"):
        start = offset or 0
        end = None if limit is None else start + limit
        return self.articles[start:end]

    async def get_article_images(self, article_id):
        if article_id == "image":
            return [{"object_path": "articles/image.jpg"}]
        return []

    async def update_article(self, article_id, data):
        self.updated.append((article_id, data))
        return data


class ArticleQualityServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_reclassifies_existing_articles_without_deleting_them(self):
        repo = FakeArticleRepo()

        summary = await reclassify_article_content_statuses(repo)

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(summary["fallback_required"], 1)
        self.assertEqual([item[0] for item in repo.updated], ["empty", "image", "gone"])
        self.assertEqual(repo.updated[0][1]["content_fetch_status"], "failed")
        self.assertEqual(repo.updated[1][1]["content_fetch_status"], "fallback_required")
        self.assertEqual(repo.updated[2][1]["content_fetch_status"], "failed")

    async def test_reclassifies_articles_in_batches(self):
        class PagedArticleRepo(FakeArticleRepo):
            def __init__(self):
                super().__init__()
                self.articles = [
                    {"id": "a", "content": "正文"},
                    {"id": "b", "content": "正文"},
                    {"id": "c", "content": "正文"},
                ]
                self.calls = []

            async def get_articles_base(self, filters=None, limit=None, offset=None, order_by="publish_time.desc"):
                self.calls.append((limit, offset))
                return self.articles[offset : offset + limit]

        repo = PagedArticleRepo()

        summary = await reclassify_article_content_statuses(repo, batch_size=2)

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["fetched"], 3)
        self.assertEqual(repo.calls, [(2, 0), (2, 2)])

    async def test_rejects_invalid_limit_and_batch_size(self):
        repo = FakeArticleRepo()

        with self.assertRaises(ValueError):
            await reclassify_article_content_statuses(repo, limit=0)
        with self.assertRaises(ValueError):
            await reclassify_article_content_statuses(repo, batch_size=0)

    async def test_continues_when_single_update_fails(self):
        class FailingUpdateRepo(FakeArticleRepo):
            async def update_article(self, article_id, data):
                if article_id == "image":
                    raise RuntimeError("write failed")
                return await super().update_article(article_id, data)

        repo = FailingUpdateRepo()

        summary = await reclassify_article_content_statuses(repo, batch_size=2)

        self.assertEqual(summary["updated"], 2)
        self.assertEqual(summary["update_failed"], 1)
        self.assertEqual([item[0] for item in repo.updated], ["empty", "gone"])
        failed_items = [item for item in summary["items"] if item["id"] == "image"]
        self.assertIn("update_error", failed_items[0])

    async def test_counts_unexpected_status_without_dropping_it(self):
        repo = FakeArticleRepo()

        with patch(
            "core.articles.quality_service.build_content_quality_update",
            return_value={"content_fetch_status": "partial", "content_fetch_error": ""},
        ):
            summary = await reclassify_article_content_statuses(repo, dry_run=True, batch_size=2)

        self.assertEqual(summary["partial"], 3)


if __name__ == "__main__":
    unittest.main()
