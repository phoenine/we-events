from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
INITIAL = ROOT / "supabase/migrations/20241120_initial_schema.sql"


class InitialSchemaParityTest(unittest.TestCase):
    def test_initial_schema_contains_activity_image_ocr_cache(self):
        sql = INITIAL.read_text().lower()
        for column in (
            "ocr_status",
            "ocr_text",
            "ocr_confidence",
            "ocr_provider",
            "ocr_error",
            "ocr_finished_at",
        ):
            with self.subTest(column=column):
                self.assertIn(column, sql)
        self.assertIn(
            "ocr_status in ('pending', 'completed', 'failed')", sql
        )
        self.assertIn("idx_article_images_ocr_status", sql)


if __name__ == "__main__":
    unittest.main()
