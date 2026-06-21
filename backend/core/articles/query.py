from typing import Literal

ArticleSortField = Literal["publish_time", "activity_extraction_status"]
SortOrder = Literal["asc", "desc"]
ActivityExtractionStatus = Literal[
    "pending",
    "queued",
    "processing",
    "fallback_required",
    "failed",
    "not_activity",
    "extracted",
]

SORT_COLUMNS = {
    "publish_time": "publish_time",
    "activity_extraction_status": "activity_extraction_status",
}


def build_article_filters(
    wechat_account_id: str | None,
    activity_extraction_status: str | None,
) -> dict:
    filters: dict = {}
    if wechat_account_id:
        filters["wechat_account_id"] = wechat_account_id
    if activity_extraction_status:
        filters["activity_extraction_status"] = activity_extraction_status

    return filters


def build_article_order(sort_by: ArticleSortField, sort_order: SortOrder) -> str:
    primary = f"{SORT_COLUMNS[sort_by]}.{sort_order}"
    if sort_by == "activity_extraction_status":
        return f"{primary},publish_time.desc"
    return primary
