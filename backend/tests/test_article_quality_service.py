import unittest

from core.articles.quality_service import reclassify_article_content_statuses


class FakeArticleRepo:
    def __init__(self):
        self.updated = []

    async def get_articles_base(self, filters=None, limit=None, offset=None, order_by="publish_time.desc"):
        return [
            {"id": "empty", "content": "暂无正文", "content_md": "", "url": "https://example.com/empty"},
            {"id": "image", "content": "", "content_md": "", "url": "https://example.com/image"},
            {"id": "gone", "content": "该内容已被发布者删除", "content_md": ""},
        ]

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


if __name__ == "__main__":
    unittest.main()
