from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
INITIAL = ROOT / "supabase/migrations/20241120_initial_schema.sql"
PATCH = ROOT / "supabase/migrations/20260622_scheduled_group_article_collection.sql"


class ScheduledGroupSchemaTest(unittest.TestCase):
    def test_initial_and_patch_define_schedule_contract(self):
        for path in (INITIAL, PATCH):
            sql = path.read_text()
            with self.subTest(path=path.name):
                for name in (
                    "schedule_enabled",
                    "schedule_time",
                    "collection_pages",
                    "last_scheduled_date",
                    "last_scheduled_at",
                    "last_collection_run_id",
                    "last_schedule_error",
                ):
                    self.assertIn(name, sql)
                self.assertIn("collection_pages between 1 and 5", sql.lower())
                self.assertIn(
                    "not schedule_enabled or schedule_time is not null", sql.lower()
                )
                self.assertIn("on delete set null", sql.lower())

    def test_initial_adds_run_foreign_key_after_run_table(self):
        sql = INITIAL.read_text().lower()
        run_table = sql.index(
            "create table if not exists public.article_collection_runs"
        )
        foreign_key = sql.index("foreign key (last_collection_run_id)")
        self.assertGreater(foreign_key, run_table)


if __name__ == "__main__":
    unittest.main()
