import http from "@/api/http";
import type { ApiList, WechatAccount } from "@/types/api";

export function listWechatAccounts(params?: {
  offset?: number;
  limit?: number;
  kw?: string;
}): Promise<ApiList<WechatAccount>> {
  return http.get("/wx/wechat-accounts", {
    params: {
      offset: params?.offset ?? 0,
      limit: params?.limit ?? 20,
      kw: params?.kw || undefined,
    },
  });
}

export function getWechatAccount(id: string): Promise<WechatAccount> {
  return http.get(`/wx/wechat-accounts/${id}`);
}

export function getWechatAccountByArticle(url: string) {
  return http.post("/wx/wechat-accounts/by_article", null, { params: { url } });
}

export function createWechatAccount(payload: {
  wechatAccountName: string;
  wechatAccountSourceId: string;
  logoUrl?: string;
  description?: string;
}) {
  return http.post("/wx/wechat-accounts", {
    mp_name: payload.wechatAccountName,
    wechat_account_id: payload.wechatAccountSourceId,
    avatar: payload.logoUrl,
    mp_intro: payload.description,
  });
}

export function updateWechatAccount(id: string, payload: Partial<WechatAccount>) {
  return http.put(`/wx/wechat-accounts/${id}`, payload);
}

export function deleteWechatAccount(id: string) {
  return http.delete(`/wx/wechat-accounts/${id}`);
}

export function syncWechatAccountArticles(
  id: string,
  params: { start_page?: number; end_page?: number } = {}
) {
  return http.get(`/wx/wechat-accounts/update/${id || "all"}`, {
    params: {
      start_page: params.start_page ?? 0,
      end_page: params.end_page ?? 1,
    },
  });
}

export function searchWechatAccounts(kw: string, params?: { offset?: number; limit?: number }) {
  return http.get(`/wx/wechat-accounts/search/${kw}`, {
    params: {
      offset: params?.offset ?? 0,
      limit: params?.limit ?? 20,
    },
  });
}
