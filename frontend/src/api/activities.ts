import http from "@/api/http";
import type {
  Activity,
  ActivityExtractionBatchResult,
  ActivityExtractionSummary,
  ActivityImageEnrichmentContext,
  ActivityImageEnrichmentPreview,
} from "@/types/api";

export function listActivities(params?: {
  offset?: number;
  limit?: number;
  article_id?: string;
  review_status?: string;
  event_status?: string;
  source_wechat_account_id?: string;
  date_from?: string;
  date_to?: string;
}): Promise<Activity[]> {
  return http.get("/wx/activities", {
    params: {
      offset: params?.offset ?? 0,
      limit: params?.limit ?? 100,
      article_id: params?.article_id || undefined,
      review_status: params?.review_status || undefined,
      event_status: params?.event_status || undefined,
      source_wechat_account_id: params?.source_wechat_account_id || undefined,
      date_from: params?.date_from || undefined,
      date_to: params?.date_to || undefined,
    },
  });
}

export function getActivity(id: string): Promise<Activity> {
  return http.get(`/wx/activities/${id}`);
}

export function createActivity(payload: Partial<Activity>) {
  return http.post("/wx/activities", payload);
}

export function updateActivity(id: string, payload: Partial<Activity>): Promise<Activity> {
  return http.patch(`/wx/activities/${id}`, payload);
}

export function deleteActivity(id: string) {
  return http.delete(`/wx/activities/${id}`);
}

export function extractArticleActivities(articleId: string) {
  return http.post(`/wx/activities/extract/article/${articleId}`);
}

export function getActivityExtractionRun(runId: string) {
  return http.get(`/wx/activities/extraction-runs/${runId}`);
}

export function getActivityExtractionSummary(): Promise<ActivityExtractionSummary> {
  return http.get("/wx/activities/extraction-summary");
}

export function extractPendingActivities(): Promise<ActivityExtractionBatchResult> {
  return http.post("/wx/activities/extract/pending");
}

export function getActivityImageEnrichmentContext(
  activityId: string
): Promise<ActivityImageEnrichmentContext> {
  return http.get(`/wx/activities/${activityId}/image-enrichment-context`);
}

export function previewActivityImageEnrichment(
  activityId: string
): Promise<ActivityImageEnrichmentPreview> {
  return http.post(`/wx/activities/${activityId}/image-enrichment-preview`);
}
