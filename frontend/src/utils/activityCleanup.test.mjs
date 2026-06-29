import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";


const utilityUrl = new URL("./activityCleanup.ts", import.meta.url);


test("defines ended activity cleanup interaction", async () => {
  assert.equal(existsSync(utilityUrl), true, "activity cleanup utility is missing");
  const {
    endedActivityCleanupConfirmation,
    endedActivityCleanupSuccess,
  } = await import(utilityUrl.href);

  assert.equal(
    endedActivityCleanupConfirmation(),
    "将删除数据库中全部已结束活动，且不可恢复，是否继续？"
  );
  assert.equal(endedActivityCleanupSuccess(3), "已删除 3 个活动");
});

test("uses the dedicated ended cleanup API", () => {
  const source = readFileSync(
    new URL("../api/activities.ts", import.meta.url),
    "utf8"
  );

  assert.match(source, /deleteEndedActivities/);
  assert.match(source, /http\.delete\("\/wx\/activities\/ended"\)/);
});

test("renders the ended activity cleanup action", () => {
  const source = readFileSync(
    new URL("../pages/activities/ActivitiesPage.tsx", import.meta.url),
    "utf8"
  );

  assert.match(source, /清理已结束/);
  assert.match(source, /endedActivityCleanupConfirmation/);
  assert.match(source, /current\?\.event_status === "ended"/);
  assert.match(
    source,
    /invalidateQueries\(\{ queryKey: \["activities"\] \}\)/
  );
  assert.equal(source.includes("!hasEndedActivities(activities)"), false);
});
