export interface StoredActivityExtractionRun {
  runId: string;
  articleId: string;
}

const STORAGE_KEY = "activityExtractionRuns";

function dedupeRuns(runs: StoredActivityExtractionRun[]) {
  const seen = new Set<string>();
  return runs.filter((item) => {
    if (!item.runId || seen.has(item.runId)) return false;
    seen.add(item.runId);
    return true;
  });
}

export function loadActivityExtractionRuns(): StoredActivityExtractionRun[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return dedupeRuns(
      parsed
        .map((item) => ({
          runId: String(item?.runId || ""),
          articleId: String(item?.articleId || ""),
        }))
        .filter((item) => item.runId && item.articleId)
    );
  } catch {
    return [];
  }
}

export function saveActivityExtractionRuns(runs: StoredActivityExtractionRun[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(dedupeRuns(runs)));
}

export function addActivityExtractionRun(run: StoredActivityExtractionRun) {
  const runs = loadActivityExtractionRuns();
  saveActivityExtractionRuns([...runs, run]);
}

export function removeActivityExtractionRuns(runIds: Set<string>) {
  const runs = loadActivityExtractionRuns().filter((item) => !runIds.has(item.runId));
  saveActivityExtractionRuns(runs);
  return runs;
}
