import unittest
from unittest.mock import patch

from jobs import article as article_job


class FakeStorage:
    bucket = "article-images"
    path = "articles/{article_id}/{uuid}-{filename}"

    def __init__(self):
        self.uploaded = []

    def valid(self):
        return True

    async def exists(self, path):
        return False

    async def upload_bytes(self, path, data, content_type):
        self.uploaded.append((path, data, content_type))

    def public_url(self, path):
        return f"https://storage.example/{path}"


class FakeResponse:
    headers = {"Content-Type": "image/png"}
    content = b"image-bytes"

    def raise_for_status(self):
        return None


class ArticleImageUploadTest(unittest.TestCase):
    def test_upload_article_images_retries_transient_download_failure(self):
        storage = FakeStorage()
        calls = {"count": 0}

        def fake_get(_url, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise article_job.requests.Timeout("temporary timeout")
            return FakeResponse()

        original_storage = article_job.supabase_storage_articles
        try:
            article_job.supabase_storage_articles = storage
            with patch.object(article_job.requests, "get", side_effect=fake_get):
                updated, mappings = article_job._upload_article_images(
                    {
                        "id": "a1",
                        "title": "活动报名",
                        "content": '<p><img src="https://mmbiz.qpic.cn/a.png" /></p>',
                    },
                    image_retry_count=2,
                    image_retry_backoff_seconds=0,
                )
        finally:
            article_job.supabase_storage_articles = original_storage

        self.assertEqual(calls["count"], 2)
        self.assertEqual(len(mappings), 1)
        self.assertIn("https://storage.example/articles/a1/", updated["content"])


if __name__ == "__main__":
    unittest.main()
