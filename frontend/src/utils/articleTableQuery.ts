export type ArticleSortField = "publish_time" | "activity_extraction_status";
export type SortOrder = "asc" | "desc";

export const FILTERABLE_ACTIVITY_EXTRACTION_STATUSES = [
  "pending",
  "fallback_required",
  "failed",
  "not_activity",
  "extracted",
] as const;

export interface ArticleTableQueryState {
  offset: number;
  limit: number;
  wechatAccountId?: string;
  activityExtractionStatus?: string;
  sortBy?: ArticleSortField;
  sortOrder?: SortOrder;
}

export interface ArticleListParams {
  offset: number;
  limit: number;
  wechat_account_id?: string;
  activity_extraction_status?: string;
  sort_by: ArticleSortField;
  sort_order: SortOrder;
}

export function buildArticleListParams(
  state: ArticleTableQueryState
): ArticleListParams {
  return {
    offset: state.offset,
    limit: state.limit,
    ...(state.wechatAccountId
      ? { wechat_account_id: state.wechatAccountId }
      : {}),
    ...(state.activityExtractionStatus
      ? { activity_extraction_status: state.activityExtractionStatus }
      : {}),
    sort_by: state.sortBy || "publish_time",
    sort_order: state.sortOrder || "desc",
  };
}
