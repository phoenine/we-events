from core.articles import article_repo
from core.wechat_accounts import wechat_account_repo
import json


class ArticleInfo:
    # 没有内容的文章数量
    no_content_count: int = 0
    # 有内容的文章数量
    has_content_count: int = 0
    # 所有文章数量
    all_count: int = 0
    # 不正常的文章数量
    wrong_count: int = 0
    # 公众号总数
    mp_all_count: int = 0


def laxArticle():
    info = ArticleInfo()

    # 所有文章数量
    info.all_count = article_repo.sync_count_articles()

    # 获取没有内容的文章数量 (content为空字符串或null)
    info.no_content_count = article_repo.sync_count_articles(
        filters={"content": {"is": None}}
    )

    # 有内容的文章数量
    info.has_content_count = info.all_count - info.no_content_count

    # 兼容旧统计字段（articles 已不再使用 status）
    info.wrong_count = 0

    # 公众号总数
    info.mp_all_count = wechat_account_repo.sync_count_wechat_accounts()

    return info.__dict__
    pass


# ARTICLE_INFO = laxArticle()
# print(ARTICLE_INFO)
ARTICLE_INFO: dict = {}
