import http from "@/api/http";
import type { ApiList, ConfigItem } from "@/types/api";

function normalizeConfig(item: any): ConfigItem {
  return {
    key: item?.key ?? item?.config_key ?? "",
    value: item?.value ?? item?.config_value ?? "",
    description: item?.description,
    created_at: item?.created_at,
    updated_at: item?.updated_at,
  };
}

export async function listConfigs(params?: {
  offset?: number;
  limit?: number;
}): Promise<ApiList<ConfigItem>> {
  const data: any = await http.get("/wx/configs", {
    params: {
      offset: params?.offset ?? 0,
      limit: params?.limit ?? 100,
    },
  });
  const list = Array.isArray(data?.list) ? data.list.map(normalizeConfig) : [];
  return { list, total: Number(data?.total ?? list.length) };
}

export async function getConfig(key: string): Promise<ConfigItem> {
  const data = await http.get(`/wx/configs/${key}`);
  return normalizeConfig(data);
}

export function createConfig(payload: Partial<ConfigItem>) {
  return http.post("/wx/configs", {
    config_key: payload.key,
    config_value: String(payload.value ?? ""),
    description: payload.description,
  });
}

export function updateConfig(key: string, payload: Partial<ConfigItem>) {
  return http.put(`/wx/configs/${key}`, {
    config_key: key,
    config_value: String(payload.value ?? ""),
    description: payload.description,
  });
}

export function deleteConfig(key: string) {
  return http.delete(`/wx/configs/${key}`);
}
