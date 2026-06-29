from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
INITIAL = ROOT / "supabase/migrations/20241120_initial_schema.sql"
PATCH = ROOT / "supabase/migrations/20260629_enqueue_pending_activity_extractions.sql"


class ActivityBatchSchemaTest(unittest.TestCase):
    def test_initial_and_patch_define_pending_enqueue_rpc(self):
        for path in (INITIAL, PATCH):
            with self.subTest(path=path.name):
                self.assertTrue(path.exists(), f"missing migration: {path.name}")
                sql = path.read_text().lower()
                self.assertIn("enqueue_pending_activity_extractions", sql)
                self.assertIn("for update of article skip locked", sql)
                self.assertIn("activity_extraction_status = 'pending'", sql)
                self.assertIn("status in ('queued', 'processing')", sql)
                self.assertIn("insert into public.activity_extraction_runs", sql)
                self.assertIn("activity_extraction_status = 'processing'", sql)
                self.assertIn("on conflict do nothing", sql)


if __name__ == "__main__":
    unittest.main()
