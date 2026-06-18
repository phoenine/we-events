import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from apis import activities as activities_api
from core.activities.image_enrichment import ActivityImageOcrUpstreamError
from core.activities.ocr_client import OcrConfigurationError


class ActivityImageEnrichmentApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_context_returns_missing_fields_and_image_count(self):
        context = {
            "activity": {"id": "activity-1"},
            "missing_fields": ["event_time"],
            "image_count": 2,
            "images": [],
        }
        with (
            patch(
                "apis.activities.get_image_enrichment_context",
                new=AsyncMock(return_value=context),
            ),
            patch.object(
                activities_api.runtime_settings,
                "get_bool",
                new=AsyncMock(return_value=True),
            ),
        ):
            response = await activities_api.activity_image_enrichment_context(
                "activity-1",
                _current_user={"id": "user-1"},
            )

        self.assertEqual(response["data"]["image_count"], 2)
        self.assertTrue(response["data"]["ocr_enabled"])

    async def test_preview_rejects_disabled_ocr(self):
        with patch.object(
            activities_api.runtime_settings,
            "get_bool",
            new=AsyncMock(return_value=False),
        ):
            with self.assertRaises(HTTPException) as raised:
                await activities_api.preview_activity_image_enrichment(
                    "activity-1",
                    _current_user={"id": "user-1"},
                )

        self.assertEqual(raised.exception.status_code, 409)

    async def test_preview_maps_missing_ocr_configuration_to_503(self):
        with (
            patch.object(
                activities_api.runtime_settings,
                "get_bool",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "apis.activities.build_image_enrichment_preview",
                new=AsyncMock(side_effect=OcrConfigurationError("missing key")),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await activities_api.preview_activity_image_enrichment(
                    "activity-1",
                    _current_user={"id": "user-1"},
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("OCR", raised.exception.detail["message"])

    async def test_preview_maps_all_ocr_failures_to_502(self):
        with (
            patch.object(
                activities_api.runtime_settings,
                "get_bool",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "apis.activities.build_image_enrichment_preview",
                new=AsyncMock(
                    side_effect=ActivityImageOcrUpstreamError("OCR provider failed")
                ),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await activities_api.preview_activity_image_enrichment(
                    "activity-1",
                    _current_user={"id": "admin-1", "role": "admin"},
                )

        self.assertEqual(raised.exception.status_code, 502)

    async def test_preview_returns_data_without_updating_activity(self):
        preview = {
            "activity_id": "activity-1",
            "suggestions": {"location_text": "城市展厅"},
            "evidence": [],
            "warnings": [],
            "images": [],
        }
        with (
            patch.object(
                activities_api.runtime_settings,
                "get_bool",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "apis.activities.build_image_enrichment_preview",
                new=AsyncMock(return_value=preview),
            ),
        ):
            response = await activities_api.preview_activity_image_enrichment(
                "activity-1",
                _current_user={"id": "user-1"},
            )

        self.assertEqual(
            response["data"]["suggestions"]["location_text"],
            "城市展厅",
        )


if __name__ == "__main__":
    unittest.main()
