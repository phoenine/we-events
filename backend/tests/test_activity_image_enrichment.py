import os
import unittest
from unittest.mock import patch

from core.articles.repo import ArticleRepository
from core.activities.ocr_client import (
    OcrConfigurationError,
    OpenAICompatibleOcrClient,
    build_ocr_payload,
)
from core.activities.image_enrichment import (
    ActivityImageEnrichmentError,
    ActivityImageOcrUpstreamError,
    build_image_enrichment_preview,
    missing_activity_fields,
)
from core.activities.image_enrichment_agent import parse_image_enrichment_output


class OcrClientTest(unittest.TestCase):
    def test_missing_configuration_is_rejected(self):
        with patch.dict(
            os.environ,
            {"OCR_API_KEY": "", "OCR_API_BASE": "", "OCR_MODEL": ""},
            clear=False,
        ):
            with self.assertRaises(OcrConfigurationError):
                OpenAICompatibleOcrClient.from_environment()

    def test_builds_openai_compatible_vision_payload(self):
        payload = build_ocr_payload(
            "vision-model",
            "https://example.com/poster.jpg",
        )

        self.assertEqual(payload["model"], "vision-model")
        content = payload["messages"][0]["content"]
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(
            content[1]["image_url"]["url"],
            "https://example.com/poster.jpg",
        )


class FakeArticleClient:
    def __init__(self):
        self.deleted = []
        self.upserted = []

    async def select(self, table, **kwargs):
        return [
            {
                "id": "image-row-1",
                "article_id": "article-1",
                "object_path": "articles/article-1/poster.jpg",
                "bucket": "article-images",
                "public_url": "https://example.com/poster.jpg",
                "origin_url": "https://source.example/poster.jpg",
                "ocr_status": "completed",
                "ocr_text": "cached text",
            }
        ]

    async def delete(self, table, filters):
        self.deleted.append((table, filters))
        return []

    async def upsert(self, table, rows, on_conflict=None):
        self.upserted.append((table, rows, on_conflict))
        return rows


class ArticleImageCachePersistenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_replacing_same_image_mapping_preserves_ocr_cache(self):
        client = FakeArticleClient()
        repo = ArticleRepository(client)

        await repo.replace_article_images(
            "article-1",
            [
                {
                    "object_path": "articles/article-1/poster.jpg",
                    "public_url": "https://example.com/poster.jpg",
                    "origin_url": "https://source.example/poster.jpg",
                }
            ],
        )

        self.assertEqual(client.deleted, [])
        self.assertNotIn("ocr_text", client.upserted[0][1][0])

    async def test_replacing_changed_image_source_resets_ocr_cache(self):
        client = FakeArticleClient()
        repo = ArticleRepository(client)

        await repo.replace_article_images(
            "article-1",
            [
                {
                    "object_path": "articles/article-1/poster.jpg",
                    "public_url": "https://example.com/poster.jpg",
                    "origin_url": "https://source.example/new-poster.jpg",
                }
            ],
        )

        row = client.upserted[0][1][0]
        self.assertEqual(row["ocr_status"], "pending")
        self.assertEqual(row["ocr_text"], "")
        self.assertIsNone(row["ocr_confidence"])
        self.assertEqual(row["ocr_provider"], "")
        self.assertEqual(row["ocr_error"], "")
        self.assertIsNone(row["ocr_finished_at"])


class FakeActivitiesRepo:
    def __init__(self):
        self.activity = {
            "id": "activity-1",
            "article_id": "article-1",
            "title": "春日展览",
            "event_time_text": "",
            "start_at": None,
            "location_text": "",
            "registration_method": "none",
            "registration_text": "",
            "registration_url": "",
            "evidence": [],
            "warnings": [],
        }
        self.updated = []

    async def get_activity_by_id(self, activity_id):
        return self.activity if activity_id == "activity-1" else None

    async def update_activity(self, activity_id, data):
        self.updated.append((activity_id, data))


class FakeArticlesRepo:
    def __init__(self):
        self.article = {
            "id": "article-1",
            "title": "春日展览",
            "content": "欢迎参观春日展览",
            "content_md": "欢迎参观春日展览",
        }
        self.images = [
            {
                "id": "image-1",
                "article_id": "article-1",
                "public_url": "https://example.com/one.jpg",
                "position": 1,
                "ocr_status": "completed",
                "ocr_text": "展览时间：7月1日",
                "ocr_provider": "cached",
            },
            {
                "id": "image-2",
                "article_id": "article-1",
                "public_url": "https://example.com/two.jpg",
                "position": 2,
                "ocr_status": "pending",
                "ocr_text": "",
            },
        ]
        self.image_updates = []

    async def get_articles_by_id(self, article_id):
        return [self.article] if article_id == "article-1" else []

    async def get_article_images(self, article_id):
        return list(self.images) if article_id == "article-1" else []

    async def update_article_image(self, image_id, data):
        self.image_updates.append((image_id, data))


class FakeOcrClient:
    def __init__(self, *, fail_urls=None):
        self.fail_urls = set(fail_urls or [])
        self.calls = []

    async def recognize(self, image_url):
        self.calls.append(image_url)
        if image_url in self.fail_urls:
            raise RuntimeError("OCR failed")
        from core.activities.ocr_client import OcrResult

        return OcrResult(text="地点：城市展厅", provider="fake")


class FakeEmptyOcrClient(FakeOcrClient):
    async def recognize(self, image_url):
        self.calls.append(image_url)
        from core.activities.ocr_client import OcrResult

        return OcrResult(text="", provider="fake")


class FakeSuggestionClient:
    def __init__(self):
        self.calls = []

    async def suggest(self, *, activity, article, images, missing_fields):
        self.calls.append(
            {
                "activity": activity,
                "article": article,
                "images": images,
                "missing_fields": missing_fields,
            }
        )
        return {
            "suggestions": {
                "event_time_text": "7月1日",
                "location_text": "城市展厅",
            },
            "evidence": [
                {
                    "field": "location_text",
                    "text": "地点：城市展厅",
                    "source": "image_ocr",
                    "image_ids": ["image-2"],
                }
            ],
            "warnings": [],
        }


class ActivityImageEnrichmentTest(unittest.IsolatedAsyncioTestCase):
    def test_missing_fields_only_reports_critical_gaps(self):
        missing = missing_activity_fields(
            {
                "event_time_text": "",
                "start_at": None,
                "location_text": "",
                "registration_method": "none",
                "registration_text": "",
                "registration_url": "",
                "fee_text": "",
                "audience": "",
            }
        )

        self.assertEqual(missing, ["event_time", "location"])

    def test_enrichment_output_rejects_unknown_activity_fields(self):
        output = parse_image_enrichment_output(
            '{"suggestions":{"location_text":"城市展厅","article_id":"other"},'
            '"evidence":[],"warnings":[]}'
        )

        self.assertEqual(output["suggestions"], {"location_text": "城市展厅"})

    async def test_preview_uses_cache_and_ocrs_every_uncached_image(self):
        activities = FakeActivitiesRepo()
        articles = FakeArticlesRepo()
        ocr = FakeOcrClient()
        suggestions = FakeSuggestionClient()

        preview = await build_image_enrichment_preview(
            "activity-1",
            activities_repo=activities,
            articles_repo=articles,
            ocr_client=ocr,
            suggestion_client=suggestions,
        )

        self.assertEqual(ocr.calls, ["https://example.com/two.jpg"])
        self.assertEqual(len(suggestions.calls[0]["images"]), 2)
        self.assertEqual(articles.image_updates[0][0], "image-2")
        self.assertEqual(
            articles.image_updates[0][1]["ocr_status"],
            "completed",
        )
        self.assertEqual(preview["suggestions"]["location_text"], "城市展厅")
        self.assertEqual(activities.updated, [])

    async def test_preview_continues_when_one_image_fails(self):
        activities = FakeActivitiesRepo()
        articles = FakeArticlesRepo()
        articles.images[0]["ocr_status"] = "pending"
        articles.images[0]["ocr_text"] = ""
        ocr = FakeOcrClient(fail_urls={"https://example.com/one.jpg"})
        suggestions = FakeSuggestionClient()

        preview = await build_image_enrichment_preview(
            "activity-1",
            activities_repo=activities,
            articles_repo=articles,
            ocr_client=ocr,
            suggestion_client=suggestions,
        )

        self.assertEqual(len(ocr.calls), 2)
        self.assertEqual(len(suggestions.calls[0]["images"]), 1)
        failed_updates = [
            data for image_id, data in articles.image_updates if image_id == "image-1"
        ]
        self.assertEqual(failed_updates[0]["ocr_status"], "failed")
        self.assertTrue(preview["warnings"])

    async def test_preview_reports_upstream_error_when_every_ocr_call_fails(self):
        activities = FakeActivitiesRepo()
        articles = FakeArticlesRepo()
        for image in articles.images:
            image["ocr_status"] = "pending"
            image["ocr_text"] = ""
        ocr = FakeOcrClient(
            fail_urls={image["public_url"] for image in articles.images}
        )

        with self.assertRaises(ActivityImageOcrUpstreamError):
            await build_image_enrichment_preview(
                "activity-1",
                activities_repo=activities,
                articles_repo=articles,
                ocr_client=ocr,
                suggestion_client=FakeSuggestionClient(),
            )

    async def test_preview_keeps_no_text_as_domain_error(self):
        activities = FakeActivitiesRepo()
        articles = FakeArticlesRepo()
        for image in articles.images:
            image["ocr_status"] = "pending"
            image["ocr_text"] = ""

        with self.assertRaises(ActivityImageEnrichmentError):
            await build_image_enrichment_preview(
                "activity-1",
                activities_repo=activities,
                articles_repo=articles,
                ocr_client=FakeEmptyOcrClient(),
                suggestion_client=FakeSuggestionClient(),
            )

    async def test_completed_empty_ocr_result_is_not_requested_again(self):
        activities = FakeActivitiesRepo()
        articles = FakeArticlesRepo()
        articles.images[0]["ocr_status"] = "completed"
        articles.images[0]["ocr_text"] = ""
        articles.images[1]["ocr_status"] = "completed"
        articles.images[1]["ocr_text"] = "地点：城市展厅"
        ocr = FakeOcrClient()

        await build_image_enrichment_preview(
            "activity-1",
            activities_repo=activities,
            articles_repo=articles,
            ocr_client=ocr,
            suggestion_client=FakeSuggestionClient(),
        )

        self.assertEqual(ocr.calls, [])

    async def test_preview_rejects_activity_without_images(self):
        activities = FakeActivitiesRepo()
        articles = FakeArticlesRepo()
        articles.images = []

        with self.assertRaisesRegex(ActivityImageEnrichmentError, "没有已采集图片"):
            await build_image_enrichment_preview(
                "activity-1",
                activities_repo=activities,
                articles_repo=articles,
                ocr_client=FakeOcrClient(),
                suggestion_client=FakeSuggestionClient(),
            )


if __name__ == "__main__":
    unittest.main()
