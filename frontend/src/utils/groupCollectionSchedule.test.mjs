import assert from "node:assert/strict";
import test from "node:test";

import {
  formatGroupCollectionSchedule,
  groupCollectionRunLabel,
  hasGroupCollectionResult,
} from "./groupCollectionSchedule.ts";


test("formats disabled and enabled schedules", () => {
  assert.equal(
    formatGroupCollectionSchedule({ schedule_enabled: false }),
    "未启用"
  );
  assert.equal(
    formatGroupCollectionSchedule({
      schedule_enabled: true,
      schedule_time: "00:30:00",
      collection_pages: 2,
    }),
    "每天 00:30 · 2 页"
  );
});

test("maps collection run statuses and trigger errors", () => {
  assert.equal(groupCollectionRunLabel({ status: "queued" }), "排队中");
  assert.equal(
    groupCollectionRunLabel({ status: "partial_success" }),
    "部分成功"
  );
  assert.equal(
    groupCollectionRunLabel(null, "queue unavailable"),
    "触发失败"
  );
});

test("detects whether a group has collection result details", () => {
  assert.equal(hasGroupCollectionResult({}), false);
  assert.equal(hasGroupCollectionResult({ last_scheduled_at: "2026-06-23T01:00:00Z" }), true);
  assert.equal(hasGroupCollectionResult({ last_collection_run: { status: "success" } }), true);
  assert.equal(hasGroupCollectionResult({ last_schedule_error: "queue unavailable" }), true);
});
