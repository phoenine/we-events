import http from "@/api/http";
import type { ApiList, WechatAccountGroup } from "@/types/api";

export function listWechatAccountGroups(params?: {
  offset?: number;
  limit?: number;
}): Promise<ApiList<WechatAccountGroup> | WechatAccountGroup[]> {
  return http.get("/wx/wechat-account-groups", {
    params: {
      offset: params?.offset ?? 0,
      limit: params?.limit ?? 100,
    },
  });
}

export function getWechatAccountGroup(id: string): Promise<WechatAccountGroup> {
  return http.get(`/wx/wechat-account-groups/${id}`);
}

export function createWechatAccountGroup(payload: Partial<WechatAccountGroup>) {
  return http.post("/wx/wechat-account-groups", payload);
}

export function updateWechatAccountGroup(id: string, payload: Partial<WechatAccountGroup>) {
  return http.put(`/wx/wechat-account-groups/${id}`, payload);
}

export function deleteWechatAccountGroup(id: string) {
  return http.delete(`/wx/wechat-account-groups/${id}`);
}
