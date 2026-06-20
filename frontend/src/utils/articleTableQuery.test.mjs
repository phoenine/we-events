import assert from "node:assert/strict";
import test from "node:test";

import {
  FILTERABLE_ACTIVITY_EXTRACTION_STATUSES,
  buildArticleListParams,
} from "./articleTableQuery.ts";

test("excludes transient extraction states from article filters", () => {
  assert.deepEqual(FILTERABLE_ACTIVITY_EXTRACTION_STATUSES, [
    "pending",
    "fallback_required",
    "failed",
    "not_activity",
    "extracted",
  ]);
});

test("defaults article lists to newest publish time", () => {
  assert.deepEqual(buildArticleListParams({ offset: 0, limit: 20 }), {
    offset: 0,
    limit: 20,
    sort_by: "publish_time",
    sort_order: "desc",
  });
});

test("serializes article filters without obsolete publish time ranges", () => {
  assert.deepEqual(
    buildArticleListParams({
      offset: 20,
      limit: 10,
      wechatAccountId: "account-1",
      activityExtractionStatus: "not_activity",
      publishTimeRange: [100, 200],
      sortBy: "activity_extraction_status",
      sortOrder: "asc",
    }),
    {
      offset: 20,
      limit: 10,
      wechat_account_id: "account-1",
      activity_extraction_status: "not_activity",
      sort_by: "activity_extraction_status",
      sort_order: "asc",
    }
  );
});
