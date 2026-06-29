from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
INITIAL = ROOT / "supabase/migrations/20241120_initial_schema.sql"


class ActivityBatchSchemaTest(unittest.TestCase):
    def test_initial_defines_pending_enqueue_rpc(self):
        sql = INITIAL.read_text().lower()

        self.assertIn("enqueue_pending_activity_extractions", sql)
        self.assertIn("for update of article skip locked", sql)
        self.assertIn("activity_extraction_status = 'pending'", sql)
        self.assertIn("status in ('queued', 'processing')", sql)
        self.assertIn("insert into public.activity_extraction_runs", sql)
        self.assertIn("activity_extraction_status = 'processing'", sql)
        self.assertIn("on conflict do nothing", sql)


if __name__ == "__main__":
    unittest.main()
