import inspect
import unittest

from fastapi import HTTPException

from apis import activities as activities_api
from apis import config_management as config_api
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


if __name__ == "__main__":
    unittest.main()
