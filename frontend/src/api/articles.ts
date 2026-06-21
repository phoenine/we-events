import http from "@/api/http";
import type { ApiList, Article } from "@/types/api";
import type { ArticleListParams } from "@/utils/articleTableQuery";

export function listArticles(
  params?: Partial<ArticleListParams>
): Promise<ApiList<Article>> {
  return http.get("/wx/articles", {
    params: {
      offset: params?.offset ?? 0,
      limit: params?.limit ?? 20,
      wechat_account_id: params?.wechat_account_id || undefined,
      activity_extraction_status:
        params?.activity_extraction_status || undefined,
      sort_by: params?.sort_by || "publish_time",
      sort_order: params?.sort_order || "desc",
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
