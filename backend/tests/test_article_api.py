import unittest
import inspect
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

    async def test_list_articles_applies_filters_to_rows_and_count(self):
        list_articles = AsyncMock(return_value=[])
        count_articles = AsyncMock(return_value=0)
        filters = {
            "wechat_account_id": "account-1",
            "activity_extraction_status": "not_activity",
        }
        with (
            patch.object(
                article_api.article_repo,
                "get_articles_base",
                new=list_articles,
            ),
            patch.object(
                article_api.article_repo,
                "count_articles_base",
                new=count_articles,
            ),
        ):
            await article_api.get_articles(
                wechat_account_id="account-1",
                activity_extraction_status="not_activity",
                sort_by="activity_extraction_status",
                sort_order="asc",
                offset=20,
                limit=10,
                _current_user={"id": "user-1"},
            )

        list_articles.assert_awaited_once_with(
            filters=filters,
            limit=10,
            offset=20,
            order_by="activity_extraction_status.asc,publish_time.desc",
        )
        count_articles.assert_awaited_once_with(filters=filters)

    def test_list_articles_does_not_expose_publish_time_filters(self):
        parameters = inspect.signature(article_api.get_articles).parameters

        self.assertNotIn("publish_time_from", parameters)
        self.assertNotIn("publish_time_to", parameters)


if __name__ == "__main__":
    unittest.main()
