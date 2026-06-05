import http from "@/api/http";
import type { ApiList, Article } from "@/types/api";

export function listArticles(params?: {
  offset?: number;
  limit?: number;
  wechat_account_id?: string;
}): Promise<ApiList<Article>> {
  return http.get("/wx/articles", {
    params: {
      offset: params?.offset ?? 0,
      limit: params?.limit ?? 20,
      wechat_account_id: params?.wechat_account_id || undefined,
    },
  });
}

export function getArticle(id: string): Promise<Article> {
  return http.get(`/wx/articles/${id}`);
}

export function deleteArticle(id: string) {
  return http.delete(`/wx/articles/${id}`);
}

export function deleteArticlesBatch(article_ids: string[]) {
  return http.delete("/wx/articles/batch", { data: { article_ids } });
}

export function cleanArticles() {
  return http.delete("/wx/articles/clean");
}

export function cleanDuplicateArticles() {
  return http.delete("/wx/articles/clean_duplicate_articles");
}

export function cleanExpiredArticles() {
  return http.delete("/wx/articles/clean_expired");
}
