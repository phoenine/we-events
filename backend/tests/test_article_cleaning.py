import unittest

from core.articles import cleaning


class FakeArticleRepo:
    def __init__(self):
        self.deleted_articles = []
        self.deleted_image_mappings = []

    def sync_get_articles(self, order_by="publish_time.desc"):
        return [
            {"id": "keep", "title": "Same", "wechat_account_id": "mp1"},
            {"id": "drop", "title": "Same", "wechat_account_id": "mp1"},
        ]

    def sync_delete_article(self, article_id):
        self.deleted_articles.append(article_id)

    def sync_delete_article_images_by_article(self, article_id):
        self.deleted_image_mappings.append(article_id)


class ArticleCleaningTest(unittest.TestCase):
    def test_duplicate_cleanup_removes_article_storage_and_image_mapping(self):
        repo = FakeArticleRepo()
        cleaned_storage = []

        original_repo = cleaning.article_repo
        original_storage_cleanup = getattr(cleaning, "delete_article_storage_objects_sync", None)
        try:
            cleaning.article_repo = repo
            cleaning.delete_article_storage_objects_sync = lambda article: cleaned_storage.append(article["id"]) or 2

            message, deleted_count = cleaning.clean_duplicate_articles()
        finally:
            cleaning.article_repo = original_repo
            if original_storage_cleanup is None:
                delattr(cleaning, "delete_article_storage_objects_sync")
            else:
                cleaning.delete_article_storage_objects_sync = original_storage_cleanup

        self.assertEqual(deleted_count, 1)
        self.assertIn("已清理 1 篇重复文章", message)
        self.assertEqual(cleaned_storage, ["drop"])
        self.assertEqual(repo.deleted_articles, ["drop"])
        self.assertEqual(repo.deleted_image_mappings, ["drop"])


if __name__ == "__main__":
    unittest.main()
