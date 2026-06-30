import unittest
from unittest.mock import MagicMock, patch

from driver.browser.playwright import PlaywrightController


class PlaywrightBrowserTest(unittest.TestCase):
    def test_start_browser_uses_bundled_chromium_without_chrome_channel(self):
        page = MagicMock()
        context = MagicMock()
        context.new_page.return_value = page
        browser = MagicMock()
        browser.new_context.return_value = context
        chromium = MagicMock()
        chromium.launch.return_value = browser
        driver = MagicMock()
        driver.chromium = chromium

        with patch("driver.browser.playwright.sync_playwright") as playwright:
            playwright.return_value.start.return_value = driver
            controller = PlaywrightController()
            self.assertIs(controller.start_browser(anti_crawler=False), page)

        chromium.launch.assert_called_once()
        self.assertNotIn("channel", chromium.launch.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
