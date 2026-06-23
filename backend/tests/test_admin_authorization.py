import inspect
import unittest

from fastapi import HTTPException

from apis import activities as activities_api
from apis import auth as auth_api
from apis import config_management as config_api
from apis import sys_info as sys_info_api
from apis import wechat_account_groups as groups_api
from core.integrations.supabase.auth import get_current_admin_user


class AdminAuthorizationTest(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_non_admin_user(self):
        with self.assertRaises(HTTPException) as raised:
            await get_current_admin_user({"id": "user-1", "role": "user"})

        self.assertEqual(raised.exception.status_code, 403)

    async def test_accepts_admin_user(self):
        user = {"id": "admin-1", "role": "admin", "status": "active"}

        self.assertIs(await get_current_admin_user(user), user)

    def test_ocr_preview_requires_admin_dependency(self):
        dependency = inspect.signature(
            activities_api.preview_activity_image_enrichment
        ).parameters["_current_user"].default

        self.assertIs(dependency.dependency, get_current_admin_user)

    def test_config_mutations_require_admin_dependency(self):
        for handler in (
            config_api.create_config,
            config_api.update_config,
            config_api.delete_config,
        ):
            with self.subTest(handler=handler.__name__):
                dependency = inspect.signature(handler).parameters[
                    "_current_user"
                ].default
                self.assertIs(dependency.dependency, get_current_admin_user)

    def test_wechat_qr_endpoints_require_admin_dependency(self):
        for handler in (
            auth_api.get_qrcode,
            auth_api.qr_image,
            auth_api.qr_url,
            auth_api.qr_status,
            auth_api.qr_success,
        ):
            with self.subTest(handler=handler.__name__):
                dependency = inspect.signature(handler).parameters[
                    "_current_user"
                ].default
                self.assertIs(dependency.dependency, get_current_admin_user)

    def test_system_endpoints_require_admin_dependency(self):
        for handler in (
            sys_info_api.system_resources,
            sys_info_api.get_system_info,
        ):
            with self.subTest(handler=handler.__name__):
                dependency = inspect.signature(handler).parameters[
                    "current_user"
                ].default
                self.assertIs(dependency.dependency, get_current_admin_user)

    def test_group_schedule_mutation_requires_admin_dependency(self):
        dependency = inspect.signature(
            groups_api.update_wechat_account_group_schedule
        ).parameters["_current_user"].default

        self.assertIs(dependency.dependency, get_current_admin_user)

    def test_system_info_does_not_read_raw_wechat_session(self):
        source = inspect.getsource(sys_info_api.get_system_info)

        self.assertNotIn("wx_get_session_info", source)


if __name__ == "__main__":
    unittest.main()
