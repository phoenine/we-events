export interface StoredArticleCollectionRun {
  runId: string;
}

const STORAGE_KEY = "articleCollectionRuns";

function dedupeRuns(runs: StoredArticleCollectionRun[]) {
  const seen = new Set<string>();
  return runs.filter((item) => {
    if (!item.runId || seen.has(item.runId)) return false;
    seen.add(item.runId);
    return true;
  });
}

export function loadArticleCollectionRuns(): StoredArticleCollectionRun[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return dedupeRuns(
      parsed
        .map((item) => ({ runId: String(item?.runId || "") }))
        .filter((item) => item.runId)
    );
  } catch {
    return [];
  }
}

export function saveArticleCollectionRuns(runs: StoredArticleCollectionRun[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(dedupeRuns(runs)));
}

export function addArticleCollectionRun(run: StoredArticleCollectionRun) {
  const runs = loadArticleCollectionRuns();
  saveArticleCollectionRuns([...runs, run]);
}

export function removeArticleCollectionRuns(runIds: Set<string>) {
  const runs = loadArticleCollectionRuns().filter((item) => !runIds.has(item.runId));
  saveArticleCollectionRuns(runs);
  return runs;
}
