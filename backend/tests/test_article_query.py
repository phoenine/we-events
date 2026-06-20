import unittest
from typing import get_args

from core.articles.query import (
    ActivityExtractionStatus,
    build_article_filters,
    build_article_order,
)


class ArticleQueryTest(unittest.TestCase):
    def test_exposes_only_supported_extraction_statuses(self):
        self.assertEqual(
            set(get_args(ActivityExtractionStatus)),
            {
                "pending",
                "queued",
                "processing",
                "fallback_required",
                "failed",
                "not_activity",
                "extracted",
            },
        )

    def test_builds_combined_filters(self):
        self.assertEqual(
            build_article_filters("account-1", "not_activity"),
            {
                "wechat_account_id": "account-1",
                "activity_extraction_status": "not_activity",
            },
        )

    def test_defaults_to_latest_publish_time(self):
        self.assertEqual(
            build_article_order("publish_time", "desc"),
            "publish_time.desc",
        )

    def test_maps_status_sort_to_existing_column(self):
        self.assertEqual(
            build_article_order("activity_extraction_status", "asc"),
            "activity_extraction_status.asc,publish_time.desc",
        )


if __name__ == "__main__":
    unittest.main()
