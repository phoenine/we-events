import time
import unittest

from core.articles.collection_policy import (
    ExistingArticleAction,
    classify_existing_article_action,
    should_reset_activity_extraction_after_content_repair,
    classify_article_collection_decision,
    is_older_than_cutoff,
    normalize_epoch_seconds,
)


class ArticleCollectionPolicyTest(unittest.TestCase):
    def test_normalize_epoch_seconds_accepts_seconds_and_milliseconds(self):
        self.assertEqual(normalize_epoch_seconds(1_700_000_000), 1_700_000_000)
        self.assertEqual(normalize_epoch_seconds(1_700_000_000_000), 1_700_000_000)
        self.assertIsNone(normalize_epoch_seconds(""))

    def test_is_older_than_cutoff_uses_publish_time_fields(self):
        cutoff = int(time.time()) - 7 * 24 * 60 * 60

        self.assertTrue(is_older_than_cutoff({"publish_time": cutoff - 1}, cutoff))
        self.assertFalse(is_older_than_cutoff({"publish_time": cutoff}, cutoff))
        self.assertFalse(is_older_than_cutoff({"publish_time": cutoff + 1}, cutoff))

    def test_recent_article_without_activity_keywords_is_collected(self):
        action = classify_article_collection_decision(
            {
                "aid": "a1",
                "title": "早鸟最后一周！猫猫与狗狗特展马上登陆西馆！",
                "digest": "新展即将开放",
                "publish_time": int(time.time()),
            },
            existing_article=None,
            cutoff_ts=int(time.time()) - 7 * 24 * 60 * 60,
        )

        self.assertEqual(action, ExistingArticleAction.COLLECT)

    def test_existing_article_with_good_content_is_skipped(self):
        action = classify_existing_article_action(
            {
                "id": "a1",
                "content_fetch_status": "fetched",
                "activity_extraction_status": "not_activity",
            }
        )

        self.assertEqual(action, ExistingArticleAction.SKIP)

    def test_existing_article_with_failed_content_is_repaired(self):
        action = classify_existing_article_action(
            {
                "id": "a1",
                "content_fetch_status": "failed",
                "activity_extraction_status": "pending",
            }
        )

        self.assertEqual(action, ExistingArticleAction.REPAIR_CONTENT)

    def test_successful_content_repair_resets_activity_extraction(self):
        self.assertTrue(
            should_reset_activity_extraction_after_content_repair(
                {"content_fetch_status": "failed"},
                {"content_fetch_status": "fetched"},
            )
        )
        self.assertFalse(
            should_reset_activity_extraction_after_content_repair(
                {"content_fetch_status": "fetched"},
                {"content_fetch_status": "fetched"},
            )
        )


if __name__ == "__main__":
    unittest.main()
