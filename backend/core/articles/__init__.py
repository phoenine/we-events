"""文章领域模块。"""

from core.articles.model import Article, ArticleBase
from core.articles.collection_repo import ArticleCollectionRepository
from core.articles.repo import ArticleRepository
from core.integrations.supabase.client import supabase_client


article_repo = ArticleRepository(supabase_client)
article_collection_repo = ArticleCollectionRepository(supabase_client)

__all__ = [
    "article_repo",
    "article_collection_repo",
    "Article",
    "ArticleBase",
    "ArticleRepository",
    "ArticleCollectionRepository",
]
