import unittest

from core.articles.quality import (
    ArticleContentQuality,
    build_content_quality_update,
    classify_article_content,
    content_fetch_status_for_quality,
)


class ArticleQualityTest(unittest.TestCase):
    def test_empty_article_without_images_is_failed(self):
        quality = classify_article_content({"content": "", "content_md": ""}, image_count=0)

        self.assertEqual(quality, ArticleContentQuality.EMPTY)
        self.assertEqual(content_fetch_status_for_quality(quality), "failed")

    def test_empty_article_with_images_requires_fallback(self):
        quality = classify_article_content({"content": "", "images": ["https://example.com/a.jpg"]})

        self.assertEqual(quality, ArticleContentQuality.IMAGE_ONLY)
        self.assertEqual(content_fetch_status_for_quality(quality), "fallback_required")

    def test_wechat_unavailable_article_is_failed(self):
        quality = classify_article_content({"content": "该内容已被发布者删除"})

        self.assertEqual(quality, ArticleContentQuality.INACCESSIBLE)
        self.assertEqual(content_fetch_status_for_quality(quality), "failed")

    def test_image_html_is_image_only_not_invalid(self):
        quality = classify_article_content(
            {"content": '<p><img src="https://example.com/a.jpg" /></p>'},
            image_count=1,
        )

        self.assertEqual(quality, ArticleContentQuality.IMAGE_ONLY)
        self.assertEqual(content_fetch_status_for_quality(quality), "fallback_required")

    def test_markdown_image_without_text_is_image_only(self):
        quality = classify_article_content(
            {"content_md": "![](https://example.com/a.jpg)"},
            image_count=1,
        )

        self.assertEqual(quality, ArticleContentQuality.IMAGE_ONLY)
        self.assertEqual(content_fetch_status_for_quality(quality), "fallback_required")

    def test_url_plus_empty_placeholder_without_images_is_failed(self):
        quality = classify_article_content(
            {
                "url": "https://mp.weixin.qq.com/s/example",
                "content": '<p><a href="https://mp.weixin.qq.com/s/example">https://mp.weixin.qq.com/s/example</a></p><p>暂无正文</p>',
                "content_md": "[https://mp.weixin.qq.com/s/example](https://mp.weixin.qq.com/s/example)\n\n暂无正文",
            },
            image_count=0,
        )

        self.assertEqual(quality, ArticleContentQuality.EMPTY)
        self.assertEqual(content_fetch_status_for_quality(quality), "failed")

    def test_markdown_link_text_counts_as_content(self):
        quality = classify_article_content(
            {
                "content_md": "[Release notes](https://example.com/release-notes)",
            },
            image_count=0,
        )

        self.assertEqual(quality, ArticleContentQuality.FETCHED)

    def test_quality_update_records_reason_for_image_only_fallback(self):
        update = build_content_quality_update({"content": ""}, image_count=1)

        self.assertEqual(update["content_fetch_status"], "fallback_required")
        self.assertIn("图片", update["content_fetch_error"])


if __name__ == "__main__":
    unittest.main()
