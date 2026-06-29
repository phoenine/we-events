import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";


const moduleUrl = new URL("./activityExtractionBatch.ts", import.meta.url);


test("formats one-click extraction interaction", async () => {
  assert.equal(existsSync(moduleUrl), true, "batch extraction utility is missing");
  const {
    activityExtractionBatchButtonText,
    activityExtractionBatchConfirmation,
    shouldPollActivityExtraction,
  } = await import(moduleUrl.href);

  assert.equal(activityExtractionBatchButtonText(), "一键抽取");
  assert.equal(
    activityExtractionBatchConfirmation(126),
    "即将抽取 126 篇文章，任务将在后台串行执行，是否继续？"
  );
  assert.equal(
    shouldPollActivityExtraction({
      pending_count: 1,
      processing_count: 0,
    }),
    true
  );
  assert.equal(
    shouldPollActivityExtraction({
      pending_count: 0,
      processing_count: 0,
    }),
    false
  );
});

test("does not render pending or processing counts beside the button", () => {
  const pageSource = readFileSync(
    new URL("../pages/articles/ArticlesPage.tsx", import.meta.url),
    "utf8"
  );

  assert.equal(
    pageSource.includes("待抽取 {extractionSummaryQuery.data?.pending_count"),
    false
  );
  assert.equal(
    pageSource.includes("抽取中"),
    false
  );
});
