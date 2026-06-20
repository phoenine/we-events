import assert from "node:assert/strict";
import test from "node:test";

import { removeIdsFromApiList, removeIdsFromList } from "./optimisticDelete.ts";

test("removes matching records and decrements total by actual matches", () => {
  const data = { list: [{ id: "a" }, { id: "b" }], total: 5 };

  assert.deepEqual(removeIdsFromApiList(data, ["a", "missing"]), {
    list: [{ id: "b" }],
    total: 4,
  });
});

test("leaves paginated data unchanged when no id matches", () => {
  const data = { list: [{ id: "a" }], total: 1 };

  assert.equal(removeIdsFromApiList(data, ["missing"]), data);
});

test("removes all matching ids without making total negative", () => {
  const data = { list: [{ id: "a" }, { id: "b" }], total: 1 };

  assert.deepEqual(removeIdsFromApiList(data, ["a", "b"]), {
    list: [],
    total: 0,
  });
});

test("removes a matching record from an array cache", () => {
  const data = [{ id: "a" }, { id: "b" }];

  assert.deepEqual(removeIdsFromList(data, ["b"]), [{ id: "a" }]);
});
