from __future__ import annotations
import time
import traceback
import threading
from typing import Any, Callable, Optional, TypedDict
from driver.wx.schemas import WxMpSession, WxEnvelope, WxErrorCode, WxError, WxDriverError
from driver.session.manager import SessionManager
from driver.wx.state import LoginState
from core.common.log import logger


class WxSessionInfo(TypedDict, total=False):
    """WxService.get_session_info 返回结构。

    说明：
    - session 结构使用 driver.wx_schemas.WxMpSession。
    - 其它字段为对 API 层稳定暴露的观测字段。
    """

    state: str
    error: Optional[str]
    has_code: bool
    wx_login_url: Optional[str]
    session: WxMpSession
    ext_data: Any


def _normalize_state_value(state: Any) -> str:
    """
    将状态值统一转为字符串，方便对外暴露。
    如果状态对象含有 value 属性则使用其值，否则直接转字符串。
    出现异常时返回 'unknown' 作为兜底。
    """
    try:
        if hasattr(state, "value"):
            return str(state.value)
        return str(state)
    except Exception:
        return "unknown"

def _cookies_list_to_header(cookies: Any) -> str:
    """将 driver session 中的 cookies(list[dict]) 转为 HTTP Cookie 头字符串（best-effort）。"""
    if not cookies:
        return ""
    parts: list[str] = []
    try:
        for c in cookies:
            if isinstance(c, dict):
                name = c.get("name")
                value = c.get("value")
            else:
                name = getattr(c, "name", None)
                value = getattr(c, "value", None)
            if name and value is not None:
                parts.append(f"{name}={value}")
    except Exception:
        return ""
    return "; ".join(parts)


def _ok(*, data: Any = None, state: Optional[str] = None) -> WxEnvelope:
    return {"ok": True, "data": data, "error": None, "state": state}


def _fail(
    *,
    code: WxErrorCode = "WX_INTERNAL_ERROR",
    message: str = "internal error",
    reason: Optional[str] = None,
    retryable: bool = False,
    stage: str = "service",
    state: Optional[str] = None,
    raw: Optional[str] = None,
) -> WxEnvelope:
    err: WxError = {
        "code": code,
        "message": message,
        "reason": reason,
        "retryable": retryable,
        "stage": stage,
        "raw": raw,
    }
    return {"ok": False, "data": None, "error": err, "state": state}


def _map_exception_to_error(
    e: Exception, *, stage: str, state: Optional[str]
) -> WxEnvelope:
    # best-effort 映射：先按关键字/类型归类，避免把底层异常直接暴露给上层
    if isinstance(e, WxDriverError):
        return _fail(
            code=e.code,
            message=e.message,
            reason=e.reason or str(e),
            retryable=bool(e.retryable),
            stage=getattr(e, "stage", stage) or stage,
            state=state,
            raw=getattr(e, "raw", None) or traceback.format_exc(),
        )
    msg = str(e) if e is not None else ""
    raw = traceback.format_exc()

    # Playwright/网络超时（粗匹配）
    if "Timeout" in msg or "timeout" in msg or "timed out" in msg:
        return _fail(
            code="WX_NETWORK_TIMEOUT",
            message="network timeout",
            reason=msg,
            retryable=True,
            stage=stage,
            state=state,
            raw=raw,
        )

    # 微信风控/环境异常（wx_article/页面提示常见关键字）
    if "当前环境异常" in msg or "完成验证" in msg:
        return _fail(
            code="WX_ENV_BLOCKED",
            message="environment blocked",
            reason=msg,
            retryable=False,
            stage=stage,
            state=state,
            raw=raw,
        )

    # 需要验证码/人机验证（更明确的提示）
    if "验证码" in msg or "captcha" in msg or "人机" in msg:
        return _fail(
            code="WX_CAPTCHA_REQUIRED",
            message="captcha required",
            reason=msg,
            retryable=False,
            stage=stage,
            state=state,
            raw=raw,
        )

    # 文章被删除/下架/不可访问（wx_article 常见提示）
    if "已删除" in msg or "已下架" in msg or "内容已被发布者删除" in msg:
        return _fail(
            code="WX_ARTICLE_DELETED",
            message="article deleted",
            reason=msg,
            retryable=False,
            stage=stage,
            state=state,
            raw=raw,
        )

    if "无法查看" in msg or "内容违规" in msg or "已被投诉" in msg or "已停止访问" in msg:
        return _fail(
            code="WX_ARTICLE_RESTRICTED",
            message="article restricted",
            reason=msg,
            retryable=False,
            stage=stage,
            state=state,
            raw=raw,
        )

    return _fail(
        code="WX_INTERNAL_ERROR",
        message="internal error",
        reason=msg,
        retryable=False,
        stage=stage,
        state=state,
        raw=raw,
    )


class WxService:
    """WxService 对外业务门面"""

    def __init__(self):
        self._wx = None
        try:
            from driver.wx.core import WX_API
            self._wx = WX_API
        except Exception as e:
            logger.warning(f"wx_service: 微信 Web 驱动初始化失败: {e}")

        # 会话管理器：统一负责持久化会话的读取和清理操作
        self._session = SessionManager()

        # Step 2: 注入 hooks（DB/Storage 外部依赖下沉到 service 层）
        self._try_inject_hooks()

    def _try_inject_hooks(self) -> None:
        """向 wx 核心驱动注入外部 hooks"""
        try:
            if not hasattr(self._wx, "set_hooks"):
                return

            # 延迟导入：避免在 wx_service import 阶段引入外部依赖
            def _on_state_change(state: str, qr_signed_url: Optional[str], error: Optional[str], expires_minutes: Optional[int]) -> None:
                try:
                    from core.integrations.supabase.auth_session_store import (
                        auth_session_store,
                    )

                    # 仅当 DB 可用时写入
                    if not auth_session_store.valid_session_db():
                        return

                    # 归一化为 wechat_auth_sessions.status 允许值，避免状态约束导致更新失败
                    status_map = {
                        LoginState.IDLE.value: "waiting",
                        LoginState.STARTING.value: "waiting",
                        LoginState.QR_READY.value: "waiting",
                        LoginState.WAIT_SCAN.value: "waiting",
                        LoginState.SUCCESS.value: "success",
                        LoginState.EXPIRED.value: "expired",
                        LoginState.FAILED.value: "error",
                    }
                    db_status = status_map.get(state, "error" if error else "waiting")
                    payload = {"status": db_status}
                    if qr_signed_url is not None:
                        payload["qr_signed_url"] = qr_signed_url
                    if expires_minutes is not None:
                        payload["expires_minutes"] = expires_minutes

                    # session_id 仍由 wx 驱动维护（兼容历史行为）
                    session_id = getattr(self._wx, "current_session_id", None)
                    if session_id:
                        def _do_update() -> None:
                            logger.info(
                                f"[wx-db] update wechat_auth_sessions id={session_id} payload={payload}"
                            )
                            ok = auth_session_store.update_session_sync(session_id, **payload)
                            logger.info(f"[wx-db] update result id={session_id} ok={ok}")

                        threading.Thread(target=_do_update, daemon=True).start()
                    else:
                        logger.warning(
                            f"[wx-db] skip update: missing current_session_id, state={state}"
                        )
                except Exception:
                    # best-effort：不影响主流程
                    return

            def _upload_qr_image(img_bytes: bytes) -> Optional[str]:
                try:
                    from core.integrations.supabase.storage import supabase_storage_qr

                    if not supabase_storage_qr.valid():
                        logger.warning("[wx-qr] storage invalid, skip upload")
                        return None

                    # 复用既有 async 上传实现（wx.py 侧会在事件循环中调用 hook）
                    logger.info(f"[wx-qr] upload start bytes={len(img_bytes or b'')}")
                    up = supabase_storage_qr.upload_qr(img_bytes)
                    # upload_qr 可能是 async，也可能是 sync；在这里做兼容处理
                    if hasattr(up, "__await__"):
                        from core.common.utils.async_tools import run_sync

                        up = run_sync(up)
                    if isinstance(up, dict):
                        logger.info(
                            f"[wx-qr] upload done path={up.get('path')} url={up.get('url')}"
                        )
                        return up.get("url")
                    logger.warning(f"[wx-qr] upload returned unexpected type={type(up)}")
                    return None
                except Exception as e:
                    logger.error(f"[wx-qr] upload failed: {e}")
                    return None

            # 组装 hooks 并注入
            hooks = {"on_state_change": _on_state_change, "upload_qr_image": _upload_qr_image}
            self._wx.set_hooks(hooks)
        except Exception:
            return


    def get_qr_code(
        self,
        callback: Optional[Callable[[Any, Any], None]] = None,
        notice: Optional[Callable[[], None]] = None,
    ) -> WxEnvelope:
        """启动（异步）登录流程并返回当前二维码状态"""
        try:
            ret = self._wx.GetCode(CallBack=callback, Notice=notice)
            # 读取并规范化状态（返回结构稳定）
            st_env = self.get_state()
            st = st_env.get("data") or {}
            state_str = st.get("state")

            base = {
                "need_login": state_str not in (LoginState.SUCCESS.value,),
                "code": st.get("wx_login_url"),
                "is_exists": st.get("has_code"),
                "state": state_str,
                "error": st.get("error"),
                "msg": "ok" if st.get("has_code") else "waiting",
            }
            if isinstance(ret, dict):
                for k, v in ret.items():
                    if k not in base:
                        base[k] = v

            return _ok(data=base, state=state_str)
        except Exception as e:
            # 失败时返回统一 envelope
            return _map_exception_to_error(e, stage="login", state=LoginState.IDLE.value)

    def get_state(self) -> WxEnvelope:
        """返回可观察的登录状态。

        注意：返回结构稳定，异常时返回 UNKNOWN 状态。
        """
        try:
            s = self._wx.get_state()
            data = {
                "state": _normalize_state_value(s.get("state")),
                "error": s.get("error"),
                "has_code": bool(s.get("has_code")),
                "wx_login_url": s.get("wx_login_url"),
            }
            return _ok(data=data, state=data.get("state"))
        except Exception as e:
            # 兜底：仍返回 envelope，state 以 idle 表示
            return _map_exception_to_error(e, stage="state", state=LoginState.IDLE.value)

    def wait_until_finished(
        self,
        timeout_seconds: int = 120,
        poll_interval: float = 0.8,
    ) -> WxEnvelope:
        """阻塞直到登录达到终态或超时。

        轮询查询状态，终态包括 SUCCESS / FAILED / EXPIRED。
        避免递归 Timer，使用简单循环等待。
        """
        deadline = time.monotonic() + max(1, int(timeout_seconds))
        while True:
            env = self.get_state()
            st = (env.get("data") or {}).get("state")

            if st in (
                LoginState.SUCCESS.value,
                LoginState.FAILED.value,
                LoginState.EXPIRED.value,
            ):
                return env

            if time.monotonic() >= deadline:
                return _fail(
                    code="WX_NETWORK_TIMEOUT",
                    message="timeout",
                    reason="timeout",
                    retryable=True,
                    stage="login",
                    state=st or LoginState.IDLE.value,
                )

            time.sleep(max(0.2, float(poll_interval)))

    def get_session_info(self) -> WxEnvelope:
        """返回当前会话信息（尽最大努力获取）。

        返回结构为 WxEnvelope，data 字段携带 WxSessionInfo 形状。
        """
        try:
            env_state = self.get_state()
            st = env_state.get("data") or {}
            state_str = str(st.get("state") or LoginState.IDLE.value)

            info: WxSessionInfo = {
                "state": state_str,
                "error": st.get("error"),
                "has_code": bool(st.get("has_code")),
                "wx_login_url": st.get("wx_login_url") or None,
            }

            # 尽力获取会话负载（运行时镜像）
            try:
                sess = getattr(self._wx, "SESSION", None)
                if isinstance(sess, dict):
                    info["session"] = sess  # type: ignore[typeddict-item]
            except Exception:
                pass

            try:
                ext = getattr(self._wx, "ext_data", None)
                if ext:
                    info["ext_data"] = ext
            except Exception:
                pass

            return _ok(data=info, state=state_str)
        except Exception as e:
            return _map_exception_to_error(e, stage="session", state=LoginState.IDLE.value)


    def get_cookie_header(self) -> WxEnvelope:
        """返回用于 requests 的 Cookie header 字符串（唯一出口）。

        - Cookie 来源：持久化会话（Store/SessionManager）
        - 返回结构：WxEnvelope，data 为 cookie header 字符串
        """
        try:
            sess = self._session.load_persisted_session()
            if not isinstance(sess, dict):
                return _fail(
                    code="WX_NOT_LOGGED_IN",
                    message="no persisted session",
                    reason="no persisted session",
                    retryable=True,
                    stage="session",
                    state=LoginState.IDLE.value,
                )

            cookie_header = _cookies_list_to_header(sess.get("cookies"))
            if not cookie_header:
                return _fail(
                    code="WX_NOT_LOGGED_IN",
                    message="no cookies",
                    reason="no cookies",
                    retryable=True,
                    stage="session",
                    state=LoginState.IDLE.value,
                )

            # 注意：这里 state 只是观测值；cookie header 有了并不等价于一定 SUCCESS
            return _ok(data=cookie_header, state=LoginState.IDLE.value)
        except Exception as e:
            return _map_exception_to_error(e, stage="session", state=LoginState.IDLE.value)


    def get_cookies_str(self) -> WxEnvelope:
        """get_cookie_header 的别名。"""
        return self.get_cookie_header()


    def login_with_token(
        self,
        callback: Optional[Callable[[Any, Any], None]] = None,
    ) -> WxEnvelope:
        """从 Store/SessionManager 恢复公众号会话"""
        logger.info("公众号会话恢复：尝试从 Store/SessionManager 复用登录态")

        try:
            sess = self._wx.Token(CallBack=callback)
        except Exception as e:
            return _map_exception_to_error(e, stage="login", state=LoginState.IDLE.value)

        if sess is None:
            # 读取当前状态以便判断失败类型
            env_state = self.get_state()
            st = env_state.get("data") or {}
            state_str = str(st.get("state") or LoginState.IDLE.value)
            err = st.get("error") or "session restore failed"

            code: WxErrorCode = (
                "WX_SESSION_EXPIRED" if state_str == LoginState.EXPIRED.value else "WX_NOT_LOGGED_IN"
            )

            return _fail(
                code=code,
                message="session restore failed",
                reason=str(err) if err is not None else None,
                retryable=(code != "WX_SESSION_EXPIRED"),
                stage="login",
                state=state_str,
            )

        # 成功：统一返回 session envelope
        return self.get_session_info()

    def fetch_article(self, url: str) -> WxEnvelope:
        """抓取微信公众号文章内容（唯一出口）。

        说明：
        - 统一由 wx_service 输出 WxEnvelope。
        - 底层抓取可能抛异常或返回哨兵值（如 content="DELETED"），这里统一映射为稳定错误码。
        - 避免 import 阶段副作用：wx_article 在此处懒加载导入。
        """
        # 1) 尽力读取当前登录态（用于 envelope.state 观测）
        env_state = self.get_state()
        st = env_state.get("data") or {}
        state_str = str(st.get("state") or LoginState.IDLE.value)

        try:
            # 懒加载：避免 import driver.wx.service 时引入 Playwright 相关链路
            from driver.wx.article import WXArticleFetcher

            fetcher = WXArticleFetcher()
            info = fetcher.get_article_content(url)

            # 2) 兼容旧哨兵值：content=DELETED 视为业务失败
            try:
                if isinstance(info, dict) and str(info.get("content") or "") == "DELETED":
                    return _fail(
                        code="WX_ARTICLE_DELETED",
                        message="article deleted",
                        reason="DELETED",
                        retryable=False,
                        stage="article",
                        state=state_str,
                    )
            except Exception:
                pass

            return _ok(data=info, state=state_str)
        except Exception as e:
            return _map_exception_to_error(e, stage="article", state=state_str)

    def clear_session(self, reason: str = "cleared") -> WxEnvelope:
        """清理公众号会话（统一清理策略）。

        先清理持久化会话，再调用 wx.reset_session 清理运行时镜像。
        不会关闭浏览器。
        """
        # 1) 清理持久化会话（best-effort）
        try:
            self._session.clear_persisted_session()
        except Exception:
            pass

        # 2) 清理运行时会话（通过 wx 公共接口，避免越界）
        try:
            if hasattr(self._wx, "reset_session"):
                self._wx.reset_session(reason=reason)
        except Exception:
            pass

        return self.get_state()

    def logout(self, clear_persisted: bool = True) -> WxEnvelope:
        """退出并清理公众号登录环境。

        行为：
        - 默认清理持久化会话（Phase 2：Store/SessionManager 为唯一真相源）。
        - 停止刷新/后台任务，并关闭浏览器资源。

        兼容性：
        - 参数 clear_persisted 保留仅为兼容旧调用方；当前默认会清理持久化会话。
        """
        # 1) 停止后台刷新等资源
        try:
            self._wx.cleanup_resources()
        except Exception:
            pass

        # 2) 清理会话（持久化 + 运行时镜像）
        if clear_persisted:
            self.clear_session(reason="logout")
        else:
            # 只清理运行时镜像，不动持久化
            try:
                if hasattr(self._wx, "SESSION"):
                    self._wx.SESSION = None
            except Exception:
                pass

        # 3) 关闭浏览器
        try:
            self._wx.Close()
        except Exception:
            pass

        return self.get_state()

    def shutdown(self) -> None:
        """兼容别名，调用 logout(clear_persisted=False)。"""
        self.logout(clear_persisted=False)

    def set_current_session_id(self, session_id: Optional[str]) -> None:
        """设置当前登录流程关联的会话 ID，供状态变更 hook 写库使用。"""
        try:
            self._wx.current_session_id = session_id
        except Exception:
            pass


# NOTE: 懒加载单例：避免 import 阶段实例化 WxService 引发更深层 import 链与潜在副作用。
_WX_SERVICE: Optional[WxService] = None


def _get_service() -> WxService:
    global _WX_SERVICE
    if _WX_SERVICE is None:
        _WX_SERVICE = WxService()
    return _WX_SERVICE


# --------------------------
# Module-level helpers (thin wrappers)
# --------------------------

# NOTE: 以下为模块级薄封装，方便直接调用 WxService 实例方法


def get_qr_code(
    callback: Optional[Callable[[Any, Any], None]] = None,
    notice: Optional[Callable[[], None]] = None,
) -> WxEnvelope:
    return _get_service().get_qr_code(callback=callback, notice=notice)


def get_state() -> WxEnvelope:
    return _get_service().get_state()


def wait_until_finished(timeout_seconds: int = 120, poll_interval: float = 0.8) -> WxEnvelope:
    return _get_service().wait_until_finished(
        timeout_seconds=timeout_seconds, poll_interval=poll_interval
    )


def get_session_info() -> WxEnvelope:
    return _get_service().get_session_info()


def get_cookie_header() -> WxEnvelope:
    return _get_service().get_cookie_header()

def get_cookies_str() -> WxEnvelope:
    return _get_service().get_cookies_str()


def login_with_token(callback: Optional[Callable[[Any, Any], None]] = None) -> WxEnvelope:
    return _get_service().login_with_token(callback=callback)


def fetch_article(url: str) -> WxEnvelope:
    return _get_service().fetch_article(url)


def clear_session(reason: str = "cleared") -> WxEnvelope:
    return _get_service().clear_session(reason=reason)


def logout(clear_persisted: bool = False) -> WxEnvelope:
    return _get_service().logout(clear_persisted=clear_persisted)


def shutdown() -> None:
    _get_service().shutdown()


def set_current_session_id(session_id: Optional[str]) -> None:
    _get_service().set_current_session_id(session_id)
