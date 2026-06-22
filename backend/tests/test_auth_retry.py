import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core.integrations.supabase.auth import SupabaseAuthManager


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *_args, **_kwargs):
        self.calls += 1
        return self._responses.pop(0)


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("GET", "https://example.test/auth/v1/user"),
    )


class AuthRetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_does_not_retry_deterministic_client_error(self):
        fake_client = _FakeAsyncClient([_response(401), _response(401), _response(401)])
        manager = SupabaseAuthManager()
        manager.url = "https://example.test"
        manager.anon_key = "anon"

        with (
            patch(
                "core.integrations.supabase.auth.httpx.AsyncClient",
                return_value=fake_client,
            ),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            user = await manager.get_user_by_token("expired-token")

        self.assertIsNone(user)
        self.assertEqual(fake_client.calls, 1)

    async def test_retries_server_errors(self):
        fake_client = _FakeAsyncClient([_response(500), _response(502), _response(503)])
        manager = SupabaseAuthManager()
        manager.url = "https://example.test"
        manager.anon_key = "anon"

        with (
            patch(
                "core.integrations.supabase.auth.httpx.AsyncClient",
                return_value=fake_client,
            ),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            user = await manager.get_user_by_token("token")

        self.assertIsNone(user)
        self.assertEqual(fake_client.calls, 3)


if __name__ == "__main__":
    unittest.main()
