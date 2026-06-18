import unittest

from core.integrations.wx import base


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


if __name__ == "__main__":
    unittest.main()
