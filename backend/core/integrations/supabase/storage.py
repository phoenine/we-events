import json
import uuid
import httpx

from core.integrations.supabase.settings import settings
from core.common.log import logger


class SupabaseStorage:
    def __init__(self, bucket_key: str = "qr"):
        self.url = settings.url
        self.key = settings.service_key

        bucket_conf = settings.buckets.get(bucket_key)
        if bucket_conf is None:
            raise ValueError(
                f"Bucket configuration '{bucket_key}' not found in settings.buckets"
            )

        self.bucket = bucket_conf.name
        self.path = bucket_conf.path
        self.expires = bucket_conf.expires
        self._client = httpx.AsyncClient(timeout=30.0)

    def valid(self) -> bool:
        return bool(self.url and self.key and self.bucket)

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.key}", "apikey": self.key}
        if content_type:
            h["Content-Type"] = content_type
        return h

    async def upload_bytes(
        self,
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        url = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        resp = await self._client.post(
            url,
            headers=self._headers(content_type),
            content=data,
        )
        if resp.status_code not in (200, 201):
            body = (resp.text or "")[:300]
            low = body.lower()
            # 兼容返回 400 + {"statusCode":"409","error":"Duplicate"} 的场景，按已存在处理
            if "duplicate" in low or "already exists" in low or '"409"' in low:
                logger.info(
                    f"[supabase-storage] object exists, skip upload bucket={self.bucket} path={path}"
                )
                return self.public_url(path)
            logger.error(
                f"[supabase-storage] upload failed bucket={self.bucket} path={path} "
                f"status={resp.status_code} body={body}"
            )
            raise Exception(resp.text)
        # 返回可访问 URL，而不是对象路径
        try:
            if self.expires and self.expires > 0:
                return await self.sign_url(path, self.expires)
        except Exception:
            pass
        return self.public_url(path)

    async def sign_url(self, path: str, expires: int | None = None) -> str:
        ex = expires or self.expires
        url = f"{self.url}/storage/v1/object/sign/{self.bucket}/{path}"
        body = {"expiresIn": ex}
        resp = await self._client.post(
            url,
            headers=self._headers("application/json"),
            json=body,
        )
        if resp.status_code != 200:
            raise Exception(resp.text)
        data = resp.json()
        signed = data.get("signedURL") or data.get("signedUrl") or ""
        if signed.startswith("/storage/v1/"):
            return f"{self.url}{signed}"
        # 兼容部分自部署 Supabase 返回 "/object/sign/..." 的场景
        if signed.startswith("/object/"):
            return f"{self.url}/storage/v1{signed}"
        if signed.startswith("/"):
            return f"{self.url}{signed}"
        return signed

    def public_url(self, path: str) -> str:
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"

    async def exists(self, path: str) -> bool:
        """检查对象是否存在。"""
        if not path:
            return False
        url = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        resp = await self._client.head(url, headers=self._headers())
        if resp.status_code == 200:
            return True
        if resp.status_code in (404, 400):
            return False
        # 非预期状态，按不存在处理，避免影响主流程
        return False

    async def delete_object(self, path: str) -> bool:
        """删除单个对象。对象不存在也视为成功。"""
        if not path:
            return True
        url = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        resp = await self._client.delete(url, headers=self._headers())
        if resp.status_code in (200, 204, 404):
            return True
        # 自部署 Supabase 可能返回 400 + not found，按已删除处理
        body = (resp.text or "").lower()
        if resp.status_code == 400 and ("not found" in body or "no such object" in body):
            return True
        logger.warning(
            f"[supabase-storage] delete failed bucket={self.bucket} path={path} "
            f"status={resp.status_code} body={(resp.text or '')[:300]}"
        )
        return False

    async def upload_qr(self, data: bytes) -> dict[str, str]:
        path = self.path
        if "{uuid}" in path:
            path = path.format(uuid=str(uuid.uuid4()))

        logger.info(
            f"[supabase-storage] upload_qr bucket={self.bucket} path={path} bytes={len(data or b'')}"
        )
        url = await self.upload_bytes(path, data, "image/png")

        return {"path": path, "url": url}


supabase_storage_qr = SupabaseStorage("qr")
supabase_storage_articles = SupabaseStorage("articles")
