from core.articles import article_repo
from core.articles.storage_cleanup import delete_article_storage_objects_sync
from core.common.log import logger


def clean_duplicate_articles():
    """
    清理重复的文章
    """
    try:
        # 获取所有文章
        articles = article_repo.sync_get_articles(order_by="publish_time.desc")

        # 如果没有文章，直接返回
        if not articles:
            return ("没有找到文章", 0)

        # 用于存储已检查的文章标题和wechat_account_id组合
        seen_articles = set()
        duplicates = []

        # 检查重复文章
        for article in articles:
            article_key = (article["title"], article["wechat_account_id"])
            if article_key in seen_articles:
                duplicates.append(article)
            else:
                seen_articles.add(article_key)

        # 删除重复文章
        storage_deleted_count = 0
        for duplicate in duplicates:
            logger.info(f"删除重复文章: {duplicate['title']}")
            storage_deleted_count += delete_article_storage_objects_sync(duplicate)
            article_repo.sync_delete_article(duplicate["id"])
            article_repo.sync_delete_article_images_by_article(duplicate["id"])

        return (
            f"已清理 {len(duplicates)} 篇重复文章，删除图片对象 {storage_deleted_count} 个",
            len(duplicates),
        )
    except Exception as e:
        return (f"清理重复文章失败: {str(e)}", 0)


if __name__ == "__main__":
    result = clean_duplicate_articles()
    logger.info(result)
