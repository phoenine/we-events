import os
import time
import traceback
from typing import Any, Callable, Optional, TypedDict
from threading import Lock

from driver.browser.playwright import PlaywrightController
from driver.wx.state import LoginState
from driver.session.lock import LOGIN_MUTEX, LockManager, LOCK_TTL_SECONDS
from driver.session.refresh import RefreshManager
from driver.session.manager import SessionManager
from driver.wx.schemas import WxMpSession
from core.common.log import logger

# ==================== Hooks 类型定义 ====================


class WxHooks(TypedDict, total=False):

    # 状态变化通知：可用于写 DB / 观测上报等
    on_state_change: Callable[[str, Optional[str], Optional[str], Optional[int]], None]

    # 上传二维码：输入二维码 bytes，返回可访问 URL（signed_url/公开URL均可）
    upload_qr_image: Callable[[bytes], Optional[str]]


class Wx:
    def __init__(self):
        self.lock_file_path = "data/.lock"
        self._lock = LockManager(self.lock_file_path, ttl_seconds=LOCK_TTL_SECONDS)

        self.refresh_interval = 3600 * 24
        self.wait_time = 1
        self.controller = PlaywrightController()

        # 实例状态（替代 class 变量）
        self.HasLogin = False
        # 当前会话（公众号后台 session），结构见 driver.wx.schemas.WxMpSession
        self.SESSION: WxMpSession | None = None
        # 兼容字段：二维码是否存在的“镜像值”，真实来源以 wx_login_url 为准
        self.HasCode = False
        self.isLOCK = False
        self.WX_LOGIN = "https://mp.weixin.qq.com/"
        self.WX_HOME = "https://mp.weixin.qq.com/cgi-bin/home"
        self.wx_login_url: str | None = None
        self.current_session_id: str | None = None
        self.CallBack = None
        self.Notice = None
        self.state: LoginState = LoginState.IDLE
        self.last_error: str | None = None

        # 外部依赖钩子（DB/Storage 等）：默认不注入，走内部 best-effort 降级
        self._hooks: Optional[WxHooks] = None

        # 线程锁 + 刷新管理
        self._login_lock = Lock()
        self._refresh = RefreshManager(
            refresh_interval=self.refresh_interval,
            get_controller=lambda: self.controller,
            is_logged_in=self.is_logged_in,
            # 刷新成功只更新状态，不重复执行登录成功回调/持久化
            on_refresh_success=lambda: self._set_state(LoginState.SUCCESS),
            on_expired=self._on_session_expired,
            login_lock=self._login_lock,
        )

        # SessionManager for session/cookie/token persistence and login-status sync
        self._session = SessionManager(
            get_controller=lambda: self.controller,
            get_qr_url=lambda: self.wx_login_url,
            set_logged_in=lambda v: setattr(self, "HasLogin", v),
            get_logged_in=lambda: bool(self.HasLogin),
            login_lock=self._login_lock,
        )

        # owner 信息移交 LockManager

        self.Clean()

    def _set_qr_url(self, url: str | None):
        """设置二维码 URL，并同步兼容字段 HasCode（单一真相：wx_login_url）。"""
        with self._login_lock:
            self.wx_login_url = url
            self.HasCode = bool(url)

    def set_hooks(self, hooks: Optional[WxHooks]) -> None:
        """注入/更新外部 hooks。

        - 由上层（例如 wx_service）注入，实现 DB 写入、二维码上传等外部能力下沉。
        - 不注入时，wx.py 会使用内部 best-effort 降级逻辑（保持当前行为）。
        """
        self._hooks = hooks

    def _emit_state_change_hook(
        self,
        *,
        state: LoginState,
        error: str | None,
        qr_signed_url: str | None,
        expires_minutes: int | None,
    ) -> None:
        """触发状态变化 hook（best-effort）。

        优先：如果注入了 hooks.on_state_change，则使用之；
        否则：直接跳过（由 wx_service 负责注入外部能力）。
        """
        # 1) 外部注入优先
        try:
            hooks = self._hooks or {}
            cb = hooks.get("on_state_change")
            if cb is not None:
                cb(state.value, qr_signed_url, error, expires_minutes)
                return
        except Exception:
            # hook 异常不得影响主流程
            return

        # 2) 未注入 hook：直接跳过（wx.py 不再直接依赖外部 DB）。
        return

    def _upload_qr_hook(self, img_bytes: bytes) -> Optional[str]:
        """上传二维码 hook（best-effort）。

        优先：如果注入了 hooks.upload_qr_image，则使用之；
        否则：直接跳过（由 wx_service 负责注入外部能力）。

        Returns:
            url: 上传后的可访问 URL（可能为 signed url）。失败返回 None。
        """
        # 1) 外部注入优先
        try:
            hooks = self._hooks or {}
            cb = hooks.get("upload_qr_image")
            if cb is not None:
                return cb(img_bytes)
        except Exception:
            return None

        # 2) 未注入 hook：直接跳过（wx.py 不再直接依赖外部 Storage）。
        return None

    def GetHasCode(self):
        # 单一真相：wx_login_url；HasCode 仅为兼容镜像
        return bool(self.wx_login_url)

    def extract_token_from_requests(self):
        """历史遗留接口：token 已下线。

        说明：公众号会话以 cookies 为唯一依据；此方法仅为兼容旧调用点保留。
        """
        return None

    def format_token(self, cookies: Any, token: str = "") -> WxMpSession:
        """兼容旧接口：将 cookies 格式化为 session dict（token 已下线）。"""
        return self._session.format_session(cookies)

    def GetCode(self, CallBack=None, Notice=None):
        self.Notice = Notice
        self._set_state(LoginState.STARTING)

        # Phase B: fast-path 统一收口
        fast = self._code_fastpath_if_logged_in()
        if fast is not None:
            return fast

        # Phase0: 封死并发窗口——在启动线程前抢占进程内互斥与跨进程锁
        acquired = LOGIN_MUTEX.acquire(blocking=False)
        if not acquired:
            logger.warning("已有登录任务在进行中，跳过本次调用")
            self._set_state(LoginState.WAIT_SCAN)
            return {
                "code": self.wx_login_url,
                "is_exists": self.GetHasCode(),
                "msg": "已有登录任务在进行中",
            }

        if not self.set_lock():
            # 未获得跨进程锁，释放进程内互斥并返回
            try:
                LOGIN_MUTEX.release()
            except Exception:
                pass
            logger.warning(
                f"微信公众平台登录脚本正在运行，请勿重复运行 lock={self._lock.debug_snapshot()}"
            )
            self._set_state(LoginState.WAIT_SCAN)
            return {
                "code": self.wx_login_url,
                "is_exists": self.GetHasCode(),
                "msg": "微信公众平台登录任务正在运行",
            }

        self.Clean()
        logger.info("子线程执行中")
        from core.common.thread import ThreadManager

        self.thread = ThreadManager(
            target=self.wxLogin, args=(CallBack, True, True, True)
        )  # args: (CallBack, NeedExit, prelocked, mutex_acquired)
        try:
            self.thread.start()  # 启动线程
        except Exception as e:
            # 若线程未能启动，必须回滚互斥与跨进程锁，避免锁遗留
            logger.warning(f"启动登录线程失败: {str(e)}")
            self._set_state(LoginState.FAILED, error=str(e))
            try:
                LOGIN_MUTEX.release()
            except Exception:
                pass
            self.release_lock()
            return {
                "code": self.wx_login_url,
                "is_exists": self.GetHasCode(),
                "msg": "启动登录线程失败",
            }

        logger.info("微信公众平台登录 v1.34")
        return self.QRcode()

    def QRcode(self):
        return {
            "code": self.wx_login_url,
            "is_exists": self.GetHasCode(),
        }

    def _set_state(
        self,
        state: LoginState,
        *,
        error: str | None = None,
        qr_signed_url: str | None = None,
        expires_minutes: int | None = None,
    ):
        """Phase 2: 统一状态切换入口（内存 + DB best-effort）"""
        with self._login_lock:
            self.state = state
            self.last_error = error
        logger.info(
            f"[wx-state] state={state.value} has_code={bool(self.wx_login_url)} "
            f"session_id={self.current_session_id} error={error or ''}"
        )
        # 外部可插拔：状态变化上报（默认仍保持原有 DB best-effort 行为）
        self._emit_state_change_hook(
            state=state,
            error=error,
            qr_signed_url=qr_signed_url,
            expires_minutes=expires_minutes,
        )

    def get_state(self) -> dict:
        """对外可观测状态"""
        with self._login_lock:
            return {
                "state": self.state.value,
                "error": self.last_error,
                "has_code": self.GetHasCode(),
                "wx_login_url": self.wx_login_url,
            }

    def is_logged_in(self) -> bool:
        """Canonical login check.

        We treat `LoginState.SUCCESS` as the only logged-in terminal state.
        Avoid using legacy `driver.success.getStatus`.
        """
        with self._login_lock:
            return self.state == LoginState.SUCCESS

    def _on_session_expired(self):
        """会话失效统一处理：状态机 + 停止刷新 + 清理会话"""
        self._set_state(LoginState.EXPIRED, error="登录已过期")
        try:
            self._refresh.stop()
        except Exception:
            pass
        try:
            self._session.clear()
        except Exception:
            pass

    def refresh_task(self):
        try:
            self._refresh.refresh_once()
        except Exception as e:
            # 保留原始异常信息，便于排障
            raise Exception(f"浏览器关闭: {str(e)}")

    def schedule_refresh(self):
        # 兼容旧接口：启动定时刷新
        self._refresh.start()

    def _cancel_refresh_timer(self):
        try:
            self._refresh.stop()
        except Exception:
            pass

    def Token(self, CallBack=None):
        """尝试从持久化存储恢复公众号登录态（基于 Store/SessionManager）。

        说明：
        - 这是“免扫码复用会话”的入口：优先从 Store 读取 cookies 并注入浏览器。
        - 若不存在可用会话，则回退为扫码登录流程。
        """
        try:
            self.CallBack = CallBack

            # 1) 从 Store/SessionManager 加载持久化会话
            persisted = self._session.load_persisted_session()
            # persisted: WxMpSession | None
            if not persisted:
                logger.warning("未找到可用的持久化会话，请先扫码登录")
                # 异步拉起二维码生成，不阻塞当前调用
                self.GetCode(CallBack=CallBack, Notice=None)
                return {
                    "need_login": True,
                    "message": "未找到可用的会话，请扫码登录后重试。",
                    "code": self.wx_login_url,
                    "is_exists": self.GetHasCode(),
                }

            cookies = persisted.get("cookies") if persisted else None

            # 2) 启动浏览器并注入 cookies
            driver = self.controller
            driver.start_browser()

            # cookies 优先使用 Playwright 列表格式；必要时做一次 normalize
            cookie_list = self._session.normalize_cookie_list(cookies or [])
            if cookie_list:
                driver.add_cookies(cookie_list)

            # 3) 打开主页验证会话（基于 cookies）
            driver.open_url(self.WX_HOME)

            page = driver.page
            if page is None:
                logger.error("页面未初始化，无法操作")
                return None

            # 若会话有效，通常能进入 home；否则会回到登录页
            try:
                page.wait_for_url(self.WX_HOME + "*", timeout=15_000)
            except Exception:
                # 尝试判断是否落在登录页（降级容错）
                cur = ""
                try:
                    cur = page.url or ""
                except Exception:
                    cur = ""
                if "mp.weixin.qq.com" in cur and "cgi-bin" not in cur:
                    # 很可能回到了登录页
                    logger.warning("持久化会话已失效，需要重新扫码")
                    self._set_state(LoginState.EXPIRED, error="持久化会话已失效")
                    self.GetCode(CallBack=CallBack, Notice=None)
                    return {
                        "need_login": True,
                        "message": "会话已过期，请扫码登录后重试。",
                        "code": self.wx_login_url,
                        "is_exists": self.GetHasCode(),
                    }

            # 4) 复用成功：走统一成功回调（会重新抓取 cookies 并持久化）
            return self.Call_Success(schedule_refresh=False)
        except Exception as e:
            logger.error(f"Token/会话复用失败: {str(e)}")
            return None
        finally:
            self.Close()

    def isLock(self):
        """二维码是否已生成且有效（兼容旧名）"""
        try:
            return self.isLOCK and bool(self.wx_login_url)
        except Exception:
            return False

    # Phase B: wxLogin 拆分为可维护的私有步骤（不改变行为，仅拆结构）
    def _ensure_thread_event_loop(self):
        """sync Playwright 不需要显式创建 event loop，避免干扰其内部循环。"""
        return

    def _fastpath_if_logged_in(self, CallBack=None) -> WxMpSession | None:
        """会话仍有效时的快速路径：复用现有会话并跳过登录流程。"""
        if self.is_logged_in():
            logger.info("检测到会话仍有效，跳过登录流程")
            self.CallBack = CallBack
            return self.Call_Success()
        return None

    def _code_fastpath_if_logged_in(self):
        """GetCode 的快速路径：会话仍有效时返回与 GetCode 一致的结构。"""
        if not self.is_logged_in():
            return None
        logger.info("检测到会话仍有效，无需重新扫码")
        self._set_state(LoginState.SUCCESS)
        return {
            "code": self.wx_login_url,
            "is_exists": self.GetHasCode(),
            "msg": "会话仍有效",
        }

    def _acquire_login_guards(
        self, *, prelocked: bool, mutex_acquired: bool
    ) -> tuple[bool, bool, bool]:
        """抢占进程内互斥 + 跨进程锁。

        Returns:
            guard_ok: 是否通过守卫（含跨进程锁）。失败时不应继续登录流程。
            mutex_held_by_me: 是否需要在 finally 中释放 LOGIN_MUTEX。
            lock_held_by_me: 是否需要在 finally 中释放跨进程锁文件。
        """
        mutex_held_by_me = False
        lock_held_by_me = False

        # Phase0: 若 GetCode 已预先抢占互斥，则这里不重复抢占，但 wxLogin
        # 仍然负责在 finally 中释放这次登录任务持有的锁。
        if mutex_acquired:
            mutex_held_by_me = True
        else:
            if self.check_lock():
                logger.warning("微信公众平台登录脚本正在运行，请勿重复运行")
                return (False, False, False)
            mutex_held_by_me = LOGIN_MUTEX.acquire(blocking=False)
            if not mutex_held_by_me:
                logger.warning("已有登录任务在进行中，跳过本次调用")
                return (False, False, False)

        if prelocked:
            lock_held_by_me = True
        else:
            ok = self.set_lock()
            lock_held_by_me = True if ok else False
            if not ok:
                logger.warning("微信公众平台登录脚本正在运行，请勿重复运行")
                return (False, mutex_held_by_me, False)

        return (True, mutex_held_by_me, lock_held_by_me)

    def _reset_login_flags(self):
        """重置登录相关的实例标志。"""
        with self._login_lock:
            self.HasLogin = False
        self._set_state(LoginState.STARTING)

    def _start_browser_and_open_login(self):
        """启动浏览器并打开登录页，返回 page。"""
        driver = self.controller
        logger.info("正在启动浏览器...")
        # 显式使用 firefox，避免系统 Chrome 依赖
        for i in range(2):
            try:
                driver.start_browser(anti_crawler=False, browser_name="firefox")
                break
            except Exception as e:
                if i == 1:
                    raise
                logger.warning(f"浏览器启动失败，第{i+1}次重试: {e}")
                try:
                    driver.cleanup()
                except Exception:
                    pass
                time.sleep(1.0)

        driver.open_url(self.WX_LOGIN)
        page = driver.page
        if page is None:
            logger.error("页面未初始化，无法操作二维码")
            raise Exception("页面未初始化，无法操作二维码")

        logger.info("正在加载登录页面...")
        page.wait_for_load_state("domcontentloaded")
        return page

    def _capture_qr_screenshot(self, page):
        """定位二维码并截图，返回 bytes。"""
        qr_tag = "img.login__type__container__scan__qrcode"
        qrcode = page.wait_for_selector(qr_tag, state="visible", timeout=15000)
        if qrcode is None:
            raise Exception("未找到登录二维码图片元素")

        # 等待二维码图片真正加载完成，避免截到白板占位图
        page.wait_for_function(
            """(selector) => {
                const img = document.querySelector(selector);
                if (!img) return false;
                const src = img.getAttribute("src") || "";
                return img.complete &&
                    img.naturalWidth > 60 &&
                    img.naturalHeight > 60 &&
                    src.includes("scanloginqrcode");
            }""",
            arg=qr_tag,
            timeout=15000,
        )

        src = qrcode.get_attribute("src") or ""
        logger.info(f"[wx-qr] img src={src}")
        img_bytes = qrcode.screenshot()
        head = img_bytes[:8].hex() if img_bytes else ""
        logger.info(
            f"[wx-qr] captured selector={qr_tag} bytes={len(img_bytes or b'')} head={head}"
        )
        try:
            os.makedirs("data/cache", exist_ok=True)
            ts = int(time.time() * 1000)
            qr_file = f"data/cache/qr-{ts}.png"
            page_file = f"data/cache/qr-page-{ts}.png"
            with open(qr_file, "wb") as f:
                f.write(img_bytes or b"")
            page.screenshot(path=page_file, full_page=True)
            logger.info(f"[wx-qr] debug saved qr={qr_file} page={page_file}")
        except Exception as e:
            logger.warning(f"[wx-qr] debug save failed: {e}")
        if not img_bytes or len(img_bytes) <= 364:
            raise Exception("二维码图片获取失败，请重新扫码")
        return img_bytes

    def _upload_qr_if_possible(self, img_bytes: bytes):
        """上传二维码（best-effort），并写入 qr_ready 状态。

        说明：
        - 优先使用外部注入 hooks.upload_qr_image。
        - 未注入时：不会上传二维码，仅维持本地流程（wx_login_url 可能为空）。
        """
        url = self._upload_qr_hook(img_bytes)
        if url:
            self._set_qr_url(url)
            self._set_state(
                LoginState.QR_READY, qr_signed_url=self.wx_login_url, expires_minutes=2
            )

    def _wait_for_scan_and_login(self, page):
        """等待扫码登录并跳转到首页。"""
        self._set_state(LoginState.WAIT_SCAN)
        logger.info("等待扫码登录...")
        if self.Notice is not None:
            self.Notice()

        logger.info(
            f"[wx-login] wait_for_url target=contains('/cgi-bin/home') timeout_ms=120000 current_url={getattr(page, 'url', '')}"
        )
        try:
            page.wait_for_url(
                lambda url: "/cgi-bin/home" in str(url),
                timeout=120000,
                wait_until="domcontentloaded",
            )
        except Exception as e:
            try:
                current_url = page.url
            except Exception:
                current_url = ""
            try:
                ready_state = page.evaluate("() => document.readyState")
            except Exception:
                ready_state = "unknown"
            try:
                title = page.title()
            except Exception:
                title = ""
            try:
                os.makedirs("data/cache", exist_ok=True)
                ts = int(time.time() * 1000)
                fail_page = f"data/cache/login-timeout-{ts}.png"
                page.screenshot(path=fail_page, full_page=True)
                logger.warning(
                    f"[wx-login] wait_for_url failed err={e} current_url={current_url} ready_state={ready_state} title={title} screenshot={fail_page}"
                )
            except Exception:
                logger.warning(
                    f"[wx-login] wait_for_url failed err={e} current_url={current_url} ready_state={ready_state} title={title}"
                )
            raise
        # 注意：此处仅表示扫码/确认已完成并进入后台主页，
        # 不应提前标记 SUCCESS。SUCCESS 由 Call_Success 在会话构建并校验后统一设置，
        # 避免前端基于“过早 success”触发收尾导致 cookies 未持久化。
        logger.info("扫码确认完成, 正在获取cookie和token...")

    def _close_event_loop_if_needed(self, NeedExit: bool):
        """sync Playwright 自行管理循环，这里不做额外关闭。"""
        return

    def wxLogin(
        self,
        CallBack=None,
        NeedExit=False,
        prelocked: bool = False,
        mutex_acquired: bool = False,
    ):
        """
        微信公众平台登录流程：
        1. 检查依赖和环境
        2. 打开微信公众平台
        3. 全屏截图保存二维码
        4. 等待用户扫码登录
        5. 获取登录后的cookie和token
        6. 启动定时刷新线程(默认30分钟刷新一次)
        """

        # 使用上下文管理器确保资源清理

        mutex_held_by_me = False
        lock_held_by_me = False
        try:
            self._ensure_thread_event_loop()

            # 快速路径：会话仍有效
            fast = self._fastpath_if_logged_in(CallBack=CallBack)
            if fast is not None:
                return fast

            guard_ok, mutex_held_by_me, lock_held_by_me = self._acquire_login_guards(
                prelocked=prelocked, mutex_acquired=mutex_acquired
            )
            if not guard_ok:
                # 未获得互斥/锁，直接退出
                return None

            self._reset_login_flags()

            # 清理现有资源
            self.cleanup_resources()

            page = self._start_browser_and_open_login()

            img_bytes = self._capture_qr_screenshot(page)
            self._upload_qr_if_possible(img_bytes)

            # waiting 状态与二维码信息已由 _set_state(LoginState.QR_READY/WAIT_SCAN) 统一更新
            self._wait_for_scan_and_login(page)

            self.CallBack = CallBack
            self.Call_Success()
            # success 状态已由 _set_state(LoginState.SUCCESS) 统一更新
        except Exception as e:
            self._set_state(LoginState.FAILED, error=str(e))
            logger.error(f"登录流程异常: {str(e)}")
            try:
                logger.error(traceback.format_exc())
            except Exception:
                pass
            self._set_qr_url(None)
            self.SESSION = None
            return self.SESSION
        finally:
            self._close_event_loop_if_needed(NeedExit)

            # 释放进程内互斥锁（仅释放本函数自己 acquire 的互斥）
            if mutex_held_by_me:
                try:
                    LOGIN_MUTEX.release()
                except Exception:
                    pass

            if lock_held_by_me:
                self.release_lock()

            if NeedExit:
                self.Clean()
        return self.SESSION

    def Call_Success(self, schedule_refresh: bool = True) -> WxMpSession | None:
        """处理登录成功后的回调逻辑"""
        session, cookies, _token = self._session.build_from_controller()
        # session: WxMpSession | None
        if session is None:
            return None

        # 获取公众号扩展信息（失败不影响主流程）
        try:
            self.ext_data = self._extract_wechat_data()
        except Exception as e:
            logger.error(f"获取公众号信息失败: {str(e)}")
            self.ext_data = None

        self.SESSION = session
        logged_in = True if cookies else False
        self._session.update_login_status(logged_in)
        self._set_state(LoginState.SUCCESS if logged_in else LoginState.FAILED)

        self.Clean()
        if logged_in:
            # 持久化会话（cookies 为唯一依据）
            try:
                self._session.save_persisted_session(session)
            except Exception:
                pass
            logger.success("登录成功！")
            # 启动一次定时刷新（守护线程，内部已处理异常）
            if schedule_refresh:
                try:
                    self.schedule_refresh()
                except Exception:
                    pass
        else:
            logger.warning("未登录！")

        if self.CallBack is not None:
            try:
                self.CallBack(self.SESSION, self.ext_data)
            except Exception as e:
                # 回调失败不应影响已完成的登录流程
                logger.warning(f"登录回调执行失败: {e}")

        return self.SESSION

    def _extract_wechat_data(self):
        """提取微信公众号数据"""
        page = getattr(self.controller, "page", None)
        if page is None:
            return {}
        data = {}
        selectors = {
            "wx_app_name": [".weui-desktop_name", ".account-name"],
            "wx_logo": [".weui-desktop-account__img", ".account-avatar img"],
            "wx_read_yesterday": [
                ".weui-desktop-home-overview .weui-desktop-data-overview:nth-child(1) .weui-desktop-data-overview__desc span",
                ".data-item:nth-child(1) .number",
            ],
            "wx_share_yesterday": [
                ".weui-desktop-home-overview .weui-desktop-data-overview:nth-child(2) .weui-desktop-data-overview__desc span",
                ".data-item:nth-child(2) .number",
            ],
            "wx_watch_yesterday": [
                ".weui-desktop-home-overview .weui-desktop-data-overview:nth-child(3) .weui-desktop-data-overview__desc span",
                ".data-item:nth-child(3) .number",
            ],
            "wx_yuan_count": [".original_cnt span", ".original-count .number"],
            "wx_user_count": [
                ".weui-desktop-user_num .weui-desktop-user_sum span",
                ".user-count .number",
            ],
        }
        for key, selector_list in selectors.items():
            try:
                value = ""
                for selector in selector_list:
                    loc = page.locator(selector)
                    try:
                        if key == "wx_logo":
                            value = loc.first.get_attribute("src", timeout=2_000) or ""
                        else:
                            value = (loc.first.inner_text(timeout=2_000) or "").strip()
                    except Exception:
                        value = ""
                    if value:
                        break
                data[key] = value
                if not value:
                    logger.warning(f"获取{key}失败: 未匹配到有效元素")
            except Exception as e:
                logger.warning(f"获取{key}失败: {e}")
                data[key] = ""
        return data

    def cleanup_resources(self):
        """清理所有相关资源"""
        try:
            # 清理临时文件
            self._cancel_refresh_timer()
            self.Clean()

            # 重置状态（统一走 SessionManager）
            self._set_qr_url(None)
            self._session.clear()

            logger.info("资源清理完成")
            return True
        except Exception as e:
            logger.warning(f"资源清理失败: {str(e)}")
            return False

    def reset_session(self, reason: str = "reset") -> None:
        """重置公众号会话（仅清理运行时镜像，不触碰持久化 Store）。

        设计目的：
        - 为 wx_service 提供一个公开、稳定的“状态复位”入口，避免外部直接操作内部字段。
        - 该方法只负责清理内存态与状态机；持久化清理由 SessionManager/Store 负责。
        """
        # 1) 清理运行时镜像
        try:
            self.SESSION = None
        except Exception:
            pass

        try:
            self.current_session_id = None
        except Exception:
            pass

        try:
            self.wx_login_url = None
        except Exception:
            pass

        # 扩展信息（若存在）一并清理
        try:
            if hasattr(self, "ext_data"):
                self.ext_data = None
        except Exception:
            pass

        # 2) 状态复位（不做网络验证）
        try:
            if hasattr(self, "_set_state"):
                self._set_state(LoginState.IDLE, error=reason)
        except Exception:
            pass

    def Close(self):
        self._cancel_refresh_timer()
        rel = False
        try:
            if hasattr(self, "controller") and self.controller is not None:
                self.controller.cleanup()
                rel = True
        except Exception as e:
            logger.warning(f"浏览器关闭/清理失败: {str(e)}")
            pass
        return rel

    def Clean(self):
        """兼容保留：历史上用于清理临时状态；当前版本不再需要。"""
        return

    def expire_all_cookies(self):
        """设置所有cookie为过期状态"""
        try:
            if hasattr(self, "controller") and hasattr(self.controller, "context"):
                self.controller.context.clear_cookies()
                return True
            else:
                logger.warning("浏览器未启动，无法操作cookie")
                return False
        except Exception as e:
            logger.error(f"设置cookie过期时出错: {str(e)}")
            return False

    def check_lock(self):
        """检查锁定状态：原子锁文件 + TTL + PID 校验"""
        return self._lock.is_locked()

    def set_lock(self):
        """创建锁定文件（原子创建），写入 pid,timestamp"""
        ok = self._lock.try_acquire()
        # 旧字段语义：是否持有锁；失败时保持 False，避免误判
        self.isLOCK = True if ok else False
        return ok

    def release_lock(self):
        """删除锁定文件（仅删除自己持有的锁，避免误删他人锁）"""
        ok = self._lock.release()
        if ok:
            self.isLOCK = False
        return ok


WX_API = Wx()
