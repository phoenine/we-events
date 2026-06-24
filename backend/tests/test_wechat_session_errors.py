import unittest
from unittest.mock import patch

import requests

from core.integrations.wx import base
from core.wechat_accounts.hooks import build_wx_gather_hooks


class WechatSessionErrorTest(unittest.TestCase):
    def test_only_200003_is_classified_as_invalid_session(self):
        self.assertTrue(hasattr(base, "wechat_error_code"))
        self.assertEqual(base.wechat_error_code(200003), "Invalid Session")
        self.assertIsNone(base.wechat_error_code(-1))
        self.assertIsNone(base.wechat_error_code(200013))

    def test_invalid_session_error_runs_hook_and_propagates(self):
        calls = []
        gather = object.__new__(base.WxGather)
        gather.hooks = base.WxGatherHooks(
            on_error=lambda error, code, ctx: calls.append((error, code, ctx))
        )
        gather.cookies = "cookie=value"
        gather.token = "token"

        with self.assertRaisesRegex(Exception, "session expired"):
            gather.Error("session expired", code="Invalid Session")

        self.assertEqual(calls[0][1], "Invalid Session")

    def test_default_hook_only_clears_session_for_invalid_session(self):
        hooks = build_wx_gather_hooks()

        with patch("driver.wx.service.clear_session") as clear_session:
            hooks.on_error("请先扫码登录公众号平台", None, {})
            hooks.on_error("frequencey control", None, {})
            clear_session.assert_not_called()

            hooks.on_error("session expired", "Invalid Session", {})
            clear_session.assert_called_once()

    def test_http_context_seeds_requests_cookie_jar_from_persisted_session(self):
        session_data = {
            "cookies": [
                {
                    "name": "slave_sid",
                    "value": "persisted",
                    "domain": ".weixin.qq.com",
                    "path": "/",
                }
            ],
            "user_agent": "ua-from-login",
        }

        with (
            patch(
                "driver.wx.service.get_cookie_header",
                return_value={"ok": True, "data": "slave_sid=persisted"},
            ),
            patch("driver.session.store.Store.load_session", return_value=session_data),
        ):
            gather = base.WxGather(hooks=base.WxGatherHooks())

        self.assertEqual(gather.session.cookies.get("slave_sid"), "persisted")
        self.assertEqual(gather.headers["Cookie"], "slave_sid=persisted")

    def test_over_persists_refreshed_requests_cookies_for_next_account(self):
        gather = object.__new__(base.WxGather)
        gather.articles = []
        gather.hooks = None
        gather.token = "token"
        gather.user_agent = "ua"
        gather.session = requests.Session()
        gather.session.cookies.set(
            "slave_sid",
            "refreshed",
            domain=".weixin.qq.com",
            path="/",
        )

        with patch("driver.session.store.Store.save_session") as save_session:
            gather.Over()

        saved = save_session.call_args.args[0]
        self.assertEqual(saved["cookies"][0]["name"], "slave_sid")
        self.assertEqual(saved["cookies"][0]["value"], "refreshed")
        self.assertEqual(saved["cookies_str"], "slave_sid=refreshed; ")


if __name__ == "__main__":
    unittest.main()
