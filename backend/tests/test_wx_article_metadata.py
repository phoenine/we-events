import unittest

from driver.wx.article import WXArticleFetcher


class _MissingLogoLocator:
    @property
    def first(self):
        return self

    def get_attribute(self, _name, *, timeout):
        raise TimeoutError(f"logo missing after {timeout}ms")


class _PageWithoutFollowAvatar:
    def locator(self, _selector):
        return _MissingLogoLocator()


class WxArticleMetadataTest(unittest.TestCase):
    def test_missing_follow_avatar_does_not_fail_article_metadata(self):
        fetcher = object.__new__(WXArticleFetcher)

        logo = fetcher._extract_mp_logo(_PageWithoutFollowAvatar())

        self.assertEqual(logo, "")


if __name__ == "__main__":
    unittest.main()
