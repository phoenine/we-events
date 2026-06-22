import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from core.integrations.supabase.auth import SupabaseAuthManager
from core.integrations.supabase.client import SupabaseClient


class _Query:
    def __init__(self, data):
        self.data = data

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class _Supabase:
    def __init__(self, query):
        self.query = query

    def table(self, _name):
        return self.query


class _AuthHttpClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *_args, **_kwargs):
        return httpx.Response(
            200,
            json={"id": "user-1", "email": "user@example.com"},
            request=httpx.Request("GET", "https://example.test/auth/v1/user"),
        )


class SupabaseAsyncExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_common_client_dispatches_execute_to_worker_thread(self):
        client = SupabaseClient()
        client.client = _Supabase(_Query([{"id": "row-1"}]))
        client._initialized = True
        to_thread = AsyncMock(side_effect=lambda function: function())

        with patch("asyncio.to_thread", new=to_thread):
            rows = await client.select("articles")

        self.assertEqual(rows, [{"id": "row-1"}])
        to_thread.assert_awaited_once()

    async def test_profile_lookup_dispatches_execute_to_worker_thread(self):
        manager = SupabaseAuthManager()
        manager.url = "https://example.test"
        manager.anon_key = "anon"
        service = _Supabase(_Query([{"role": "admin", "status": "active"}]))
        to_thread = AsyncMock(side_effect=lambda function: function())

        with (
            patch(
                "core.integrations.supabase.auth.httpx.AsyncClient",
                return_value=_AuthHttpClient(),
            ),
            patch.object(manager, "get_client", return_value=service),
            patch("asyncio.to_thread", new=to_thread),
        ):
            user = await manager.get_user_by_token("token")

        self.assertEqual(user["role"], "admin")
        to_thread.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
