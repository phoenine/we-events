import http from "@/api/http";
import type { ConfigItem } from "@/types/api";

export function listConfigs(params?: { offset?: number; limit?: number }): Promise<ConfigItem[]> {
  return http.get("/wx/configs", {
    params: {
      offset: params?.offset ?? 0,
      limit: params?.limit ?? 100,
    },
  });
}

export function getConfig(key: string): Promise<ConfigItem> {
  return http.get(`/wx/configs/${key}`);
}

export function createConfig(payload: Partial<ConfigItem>) {
  return http.post("/wx/configs", payload);
}

export function updateConfig(key: string, payload: Partial<ConfigItem>) {
  return http.put(`/wx/configs/${key}`, payload);
}

export function deleteConfig(key: string) {
  return http.delete(`/wx/configs/${key}`);
}
