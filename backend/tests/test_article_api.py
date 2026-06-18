import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from apis import article as article_api


class ArticleApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        if article_api._reclassify_content_status_lock.locked():
            article_api._reclassify_content_status_lock.release()

    async def test_reclassify_rejects_concurrent_request(self):
        await article_api._reclassify_content_status_lock.acquire()

        with self.assertRaises(HTTPException) as raised:
            await article_api.reclassify_content_status(
                limit=10,
                dry_run=False,
                _current_user={"id": "admin", "role": "admin"},
            )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_reclassify_releases_lock_after_request(self):
        with patch(
            "apis.article.reclassify_article_content_statuses",
            new=AsyncMock(return_value={"total": 0}),
        ):
            await article_api.reclassify_content_status(
                limit=10,
                dry_run=True,
                _current_user={"id": "admin", "role": "admin"},
            )

        self.assertFalse(article_api._reclassify_content_status_lock.locked())


if __name__ == "__main__":
    unittest.main()
