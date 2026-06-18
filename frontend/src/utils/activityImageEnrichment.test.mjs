import assert from "node:assert/strict";
import test from "node:test";

import { isActivityEnrichmentPreviewCurrent } from "./activityImageEnrichment.ts";


test("accepts a preview only for the currently selected activity", () => {
  const selected = { id: "activity-1" };
  const matching = { activity_id: "activity-1" };
  const stale = { activity_id: "activity-2" };

  assert.equal(isActivityEnrichmentPreviewCurrent(selected, matching), true);
  assert.equal(isActivityEnrichmentPreviewCurrent(selected, stale), false);
  assert.equal(isActivityEnrichmentPreviewCurrent(null, matching), false);
});
