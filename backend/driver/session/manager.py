from __future__ import annotations
import re
from threading import Lock
from typing import Any, Callable, Optional
from core.common.log import logger
from driver.session.cookies import expire
from driver.session.store import Store
from driver.wx.schemas import WxMpSession


class SessionManager:
    """会话管理器，负责会话的构建、格式化、持久化及校验"""

    def clear(self):
        """清空登录态与会话镜像"""
        self.update_login_status(False)

    def normalize_cookie_list(self, cookies: list | None, domain: str = ".weixin.qq.com", path: str = "/") -> list:
        """为 cookie 列表补齐 domain/path 信息"""
        if not cookies:
            return []
        out = []
        for c in cookies:
            try:
                cc = dict(c)
                cc.setdefault("domain", domain)
                cc.setdefault("path", path)
                out.append(cc)
            except Exception:
                continue
        return out

    def __init__(
        self,
        get_controller: Optional[Callable[[], Any]] = None,
        get_qr_url: Optional[Callable[[], str]] = None,
        set_logged_in: Optional[Callable[[bool], None]] = None,
        get_logged_in: Optional[Callable[[], bool]] = None,
        login_lock: Optional[Lock] = None,
    ):
        """
        初始化会话管理器。

        参数说明：
        - get_controller: 返回当前浏览器控制器的回调。
        - get_qr_url: 返回二维码 URL 的回调。
        - set_logged_in: 设置登录状态的回调。
        - get_logged_in: 获取登录状态的回调。
        - login_lock: 用于登录状态更新的线程锁。
        """
        # 默认桩：避免在无 controller 场景下调用时报错
        self._get_controller = get_controller or (lambda: None)
        self._get_qr_url = get_qr_url or (lambda: "")
        self._set_logged_in = set_logged_in or (lambda _v: None)
        self._get_logged_in = get_logged_in or (lambda: False)
        self._lock = login_lock or Lock()

    def format_session(self, cookies: Any, token: Optional[str] = None) -> WxMpSession:
        """根据 cookies 构建统一的 WxMpSession 结构"""
        cookies_str = ""
        for cookie in cookies or []:
            try:
                name = str(cookie.get("name", ""))
                value = str(cookie.get("value", ""))
            except Exception:
                continue

            if name:
                cookies_str += f"{name}={value}; "
        cookie_expiry = expire(cookies or [])
        sess: WxMpSession = {
            "cookies": cookies,
            "cookies_str": cookies_str,
            "wx_login_url": self._get_qr_url(),
            "expiry": cookie_expiry,
        }
        if token:
            sess["token"] = str(token)
        return sess

    def load_persisted_session(self) -> Optional[WxMpSession]:
        """从持久化存储加载公众号会话"""
        try:
            sess = Store.load_session()
            if not sess:
                return None
            return sess
        except Exception as e:
            logger.warning(f"加载持久化会话失败: {str(e)}")
            return None

    def save_persisted_session(self, session: WxMpSession) -> None:
        """将公众号会话写入持久化存储"""
        try:
            if not session:
                return
            Store.save_session(session)
        except Exception as e:
            logger.warning(f"保存持久化会话失败: {str(e)}")

    def clear_persisted_session(self) -> None:
        """清理持久化存储中的公众号会话"""
        try:
            Store.clear_session()
        except Exception as e:
            logger.warning(f"清理持久化会话失败: {str(e)}")

    def is_session_valid(self, session: Optional[WxMpSession]) -> bool:
        """判断公众号会话是否有效"""
        if not session or not isinstance(session, dict):
            return False

        # 1) 过期信息优先
        expiry = session.get("expiry")
        if isinstance(expiry, dict):
            try:
                if bool(expiry.get("is_expired")) is True:
                    return False
            except Exception:
                pass

            # remaining_seconds / expires_in <= 0 视为过期
            for k in ("remaining_seconds", "expires_in"):
                if k in expiry:
                    try:
                        v = int(expiry.get(k) or 0)
                        if v <= 0:
                            return False
                        # 有明确剩余时间且 >0，可直接判定有效
                        return True
                    except Exception:
                        # 字段存在但不可解析，继续走 cookies 判断
                        break

        # 2) cookies 结构校验
        cookies = session.get("cookies")
        if not isinstance(cookies, list) or len(cookies) == 0:
            return False

        for c in cookies:
            if not isinstance(c, dict):
                continue
            name = c.get("name")
            value = c.get("value")
            if isinstance(name, str) and name and value is not None:
                return True

        return False

    def update_login_status(self, logged_in: bool):
        """更新 Wx.HasLogin 镜像"""
        with self._lock:
            self._set_logged_in(bool(logged_in))

    def build_from_controller(self) -> tuple[Optional[WxMpSession], Any, Optional[str]]:
        """从当前 controller 构建 session"""
        controller = self._get_controller()
        if controller is None:
            logger.error("浏览器控制器未初始化")
            return None, None, None

        try:
            cookies = controller.get_cookies()
        except Exception:
            cookies = None

        token: Optional[str] = None
        user_agent: Optional[str] = None
        try:
            page = getattr(controller, "page", None)
            page_url = getattr(page, "url", "") or ""
            m = re.search(r"[?&]token=([^&]+)", page_url)
            if m:
                token = m.group(1)
        except Exception:
            token = None

        session = self.format_session(cookies, token=token)
        try:
            page = getattr(controller, "page", None)
            if page is not None:
                ua = page.evaluate("() => navigator.userAgent")
                if ua:
                    user_agent = str(ua)
        except Exception:
            user_agent = None
        if user_agent:
            session["user_agent"] = user_agent
        return session, cookies, token
