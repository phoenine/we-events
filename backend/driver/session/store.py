from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from core.common.app_settings import settings
from driver.session.crypto import FileCrypto


class KeyStore:
    """公众号会话的唯一持久化接口，负责加密存储和读取公众号会话数据"""

    key_file = "data/wx.lic"

    def __init__(self):
        # lic_key 用于本地加密密钥；默认值仅用于开发环境
        self._crypto = FileCrypto(settings.safe_lic_key)

    def _write_json(self, obj: Any) -> None:
        # 将对象序列化为 JSON 字符串，使用 utf-8 编码写入加密文件
        text = json.dumps(obj, ensure_ascii=False)
        # 加密写入文件，保证数据安全
        self._crypto.encrypt_to_file(self.key_file, text.encode("utf-8"))

    def _read_json(self) -> Optional[Any]:
        try:
            # 从加密文件读取内容，解密后使用 utf-8 解码为字符串
            raw = self._crypto.decrypt_from_file(self.key_file)
            text = raw.decode("utf-8")
            # 空内容视为无数据，返回 None
            if not text.strip():
                return None
            # 反序列化 JSON 数据
            return json.loads(text)
        except Exception:
            # 读取异常全部吞掉，避免影响业务，但不便于排障
            return None

    def _sanitize_cookies(self, cookies: Any) -> List[dict]:
        """对 cookies 做轻度清洗"""
        if not cookies:
            return []

        if isinstance(cookies, dict):
            cookies = [cookies]
        if not isinstance(cookies, (list, tuple)):
            return []

        out: List[dict] = []
        for c in cookies:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name", "") or "")
            # 基于 name 过滤，避免统计类无用 cookie 干扰
            if name == "_clck":
                continue
            out.append(c)
        return out

    def save_session(self, session: Dict[str, Any]) -> None:
        """保存完整公众号会话到加密文件"""
        if not session or not isinstance(session, dict):
            return

        sess = dict(session)
        sess["cookies"] = self._sanitize_cookies(sess.get("cookies"))

        # 统一写入时间戳（可选字段，便于排障）
        if "updated_at" not in sess:
            try:
                import time

                sess["updated_at"] = int(time.time())
            except Exception:
                pass

        self._write_json({"type": "wx_mp_session", "session": sess})

    def load_session(self) -> Optional[Dict[str, Any]]:
        """加载完整公众号会话"""
        obj = self._read_json()
        if not obj:
            return None

        if isinstance(obj, dict) and obj.get("type") == "wx_mp_session":
            sess = obj.get("session")
            if isinstance(sess, dict):
                # 读出时再清洗一次（防止历史数据污染）
                sess = dict(sess)
                sess["cookies"] = self._sanitize_cookies(sess.get("cookies"))
                return sess
        return None

    def clear_session(self) -> None:
        """清理会话"""
        try:
            if os.path.exists(self.key_file):
                os.remove(self.key_file)
                return
        except Exception:
            pass

        # 删除失败则覆盖为空
        try:
            self._write_json({})
        except Exception:
            pass


Store = KeyStore()
