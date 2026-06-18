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

    async def test_clean_expired_deletes_articles_older_than_seven_days(self):
        clean_expired = AsyncMock(return_value=0)
        with (
            patch.object(
                article_api.article_repo,
                "get_articles_base",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                article_api.article_repo,
                "clean_expired_articles",
                new=clean_expired,
            ),
            patch(
                "apis.article._safe_delete_article_image_mappings",
                new=AsyncMock(),
            ),
        ):
            await article_api.clean_expired_articles(
                _current_user={"id": "admin", "role": "admin"}
            )

        clean_expired.assert_awaited_once_with(days=7)


if __name__ == "__main__":
    unittest.main()
