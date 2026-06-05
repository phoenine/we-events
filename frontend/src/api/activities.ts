import http from "@/api/http";
import type { Activity } from "@/types/api";

export function listActivities(params?: {
  offset?: number;
  limit?: number;
  article_id?: string;
}): Promise<Activity[]> {
  return http.get("/wx/activities", {
    params: {
      offset: params?.offset ?? 0,
      limit: params?.limit ?? 100,
      article_id: params?.article_id || undefined,
    },
  });
}

export function getActivity(id: string): Promise<Activity> {
  return http.get(`/wx/activities/${id}`);
}

export function createActivity(payload: Partial<Activity>) {
  return http.post("/wx/activities", payload);
}

export function updateActivity(id: string, payload: Partial<Activity>) {
  return http.put(`/wx/activities/${id}`, payload);
}

export function deleteActivity(id: string) {
  return http.delete(`/wx/activities/${id}`);
}

export function fetchActivities(payload: { scope?: "today" | "week" | "all"; limit?: number }) {
  return http.post("/wx/activities/fetch", payload);
}
