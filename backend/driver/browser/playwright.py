import os
import platform
import json
import random
import uuid
import threading
from playwright.sync_api import sync_playwright
from core.common.log import logger


browsers_name = os.getenv("BROWSER_TYPE", "firefox")
browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "")
if browsers_path:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path


LAUNCH_MUTEX = threading.Lock()


class PlaywrightController:
    """Playwright浏览器控制器类"""

    def __init__(self):
        self.system = platform.system().lower()
        self.driver = None
        self.browser = None
        self.context = None
        self.page = None
        self.isClose = True
        self._lock = threading.Lock()  # 实例级线程锁保护状态
        self._driver_thread_id = None

    def _is_browser_installed(self, browser_name):
        """检查指定浏览器是否已安装"""
        try:
            if not browsers_path:
                return False

            # 遍历目录，查找包含浏览器名称的目录
            for item in os.listdir(browsers_path):
                item_path = os.path.join(browsers_path, item)
                if os.path.isdir(item_path) and browser_name.lower() in item.lower():
                    return True

            return False
        except (OSError, PermissionError):
            return False

    def start_browser(
        self,
        headless=True,
        mobile_mode=False,
        dis_image=False,
        browser_name=browsers_name,
        language="zh-CN",
        anti_crawler=True,
    ):
        """启动浏览器并返回页面对象"""
        try:
            # 固定锁顺序：先进程级，再实例级，避免与 cleanup 竞争
            with LAUNCH_MUTEX:
                with self._lock:
                    # 若浏览器已启动且页面可用，直接复用，避免重复拉起
                    current_tid = threading.get_ident()
                    if self.page is not None and self.isClose is False and self._driver_thread_id == current_tid:
                        return self.page

                    current_tid = threading.get_ident()
                    # Playwright sync driver 不能跨线程复用；线程切换时强制重建
                    if (
                        self.driver is not None
                        and self._driver_thread_id is not None
                        and self._driver_thread_id != current_tid
                    ):
                        self._unsafe_cleanup_locked()

                    if bool(os.getenv("NOT_HEADLESS", False)):
                        headless = False
                    if self.driver is None:
                        self.driver = sync_playwright().start()
                        self._driver_thread_id = current_tid

                    # 轻量重试 1 次（总计 2 次），首次失败会完整清理并重建 driver
                    for i in range(2):
                        try:
                            browser_type = self.driver.firefox  # 统一使用 Firefox
                            self.browser = browser_type.launch(
                                headless=headless,
                                args=[
                                    "--no-sandbox",
                                    "--disable-dev-shm-usage",
                                    "--disable-gpu",
                                ],
                            )
                            # 启动成功后创建上下文与页面（保持在同一把实例锁内，防止并发 cleanup）
                            context_options = {"locale": language}
                            if anti_crawler:
                                context_options.update(
                                    self._get_anti_crawler_config(mobile_mode)
                                )

                            self.context = self.browser.new_context(**context_options)
                            self.page = self.context.new_page()

                            if mobile_mode:
                                self.page.set_viewport_size(
                                    {"width": 375, "height": 812}
                                )

                            if dis_image:
                                self.context.route(
                                    "**/*.{png,jpg,jpeg}", lambda route: route.abort()
                                )

                            if anti_crawler:
                                self._apply_anti_crawler_scripts()

                            self.isClose = False
                            return self.page
                        except Exception:
                            if i == 1:
                                raise
                            # 第一次失败：完整清理并重建 driver，再重试
                            try:
                                self._unsafe_cleanup_locked()
                            finally:
                                self.driver = sync_playwright().start()
                                self._driver_thread_id = current_tid
        except Exception as e:
            # 交由上层感知，同时保证本实例资源释放
            with self._lock:
                self._unsafe_cleanup_locked()
            raise Exception(f"浏览器启动失败: {str(e)}")

    def string_to_json(self, json_string):
        """将字符串解析为JSON对象"""
        try:
            json_obj = json.loads(json_string)
            return json_obj
        except json.JSONDecodeError as e:
            logger.info(f"JSON解析错误: {e}")
            return ""

    def parse_string_to_dict(self, kv_str: str):
        """将格式如 key=value;key2=value2 的字符串解析为字典"""
        result = {}
        items = kv_str.strip().split(";")
        for item in items:
            try:
                key, value = item.strip().split("=")
                result[key.strip()] = value.strip()
            except Exception as e:
                pass
        return result

    def add_cookies(self, cookies):
        """添加多条Cookie"""
        if self.context is None:
            raise Exception("浏览器未启动，请先调用 start_browser()")
        self.context.add_cookies(cookies)

    def add_cookie(self, cookie):
        """添加单条Cookie"""
        self.add_cookies([cookie])

    def get_cookies(self):
        """获取当前上下文 cookies，供会话持久化使用。"""
        if self.context is None:
            return []
        try:
            return self.context.cookies()
        except Exception:
            return []

    def _get_anti_crawler_config(self, mobile_mode=False):
        """获取反爬虫相关配置"""
        # 生成随机指纹
        fingerprint = self._generate_uuid()

        config = {
            "user_agent": self._get_realistic_user_agent(mobile_mode),
            "viewport": {
                "width": random.randint(1200, 1920) if not mobile_mode else 375,
                "height": random.randint(800, 1080) if not mobile_mode else 812,
                "device_scale_factor": random.choice([1, 1.25, 1.5, 2]),
            },
            "extra_http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            },
        }

        if mobile_mode:
            config["extra_http_headers"].update(
                {
                    "User-Agent": config["user_agent"],
                    "X-Requested-With": "com.tencent.mm",
                }
            )

        return config

    def _get_realistic_user_agent(self, mobile_mode=False):
        """获取更真实的User-Agent字符串"""
        logger.info(f"浏览器特征设置完成: {'移动端' if mobile_mode else '桌面端'}")
        if mobile_mode:
            mobile_agents = [
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
                "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
                "Mozilla/5.0 (Windows Phone 10.0; Android 6.0.1; Microsoft; Lumia 950) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36 Edge/14.14393",
            ]
            return random.choice(mobile_agents)
        else:
            desktop_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ]
            return random.choice(desktop_agents)

    def _generate_uuid(self):
        """生成UUID指纹"""
        return str(uuid.uuid4()).replace("-", "")

    def _apply_anti_crawler_scripts(self):
        """应用反爬虫脚本，尽量隐藏自动化特征"""
        # 可选依赖：未安装时不自动 pip 安装，避免运行期修改环境导致不可控
        try:
            from playwright_stealth.stealth import Stealth

            stealth = Stealth()
            stealth.apply_stealth_sync(self.page)
        except Exception:
            # 降级：仅使用下面的 init_script/evaluate 方案
            pass

        # 隐藏自动化特征
        self.page.add_init_script(
            """
        // 隐藏webdriver属性
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });

        // 隐藏chrome属性
        Object.defineProperty(window, 'chrome', {
            get: () => false,
        });

        // 修改plugins长度
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // 修改languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en'],
        });

        // 修改permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        """
        )

        # 设置更真实的浏览器行为
        self.page.evaluate(
            """
        // 随机延迟点击事件
        const originalAddEventListener = EventTarget.prototype.addEventListener;
        EventTarget.prototype.addEventListener = function(type, listener, options) {
            if (type === 'click') {
                const wrappedListener = function(...args) {
                    setTimeout(() => listener.apply(this, args), Math.random() * 100 + 50);
                };
                return originalAddEventListener.call(this, type, wrappedListener, options);
            }
            return originalAddEventListener.call(this, type, listener, options);
        };

        // 随机化鼠标移动
        document.addEventListener('mousemove', (e) => {
            if (Math.random() > 0.7) {
                e.stopImmediatePropagation();
            }
        }, true);
        """
        )

    def __del__(self):
        """对象析构时尽量清理资源"""
        try:
            if getattr(self, "isClose", True) is False:
                self.cleanup()
        except Exception:
            pass

    def open_url(self, url, wait_until="domcontentloaded"):
        """打开指定URL"""
        try:
            if self.page is None:
                raise Exception("页面未初始化，请先调用 start_browser()")
            self.page.goto(url, wait_until=wait_until)
        except Exception as e:
            raise Exception(f"打开URL失败: {str(e)}")

    def Close(self):
        """关闭浏览器"""
        self.cleanup()

    def _unsafe_cleanup_locked(self):
        """
        在已持有实例级锁的前提下清理资源。

        说明：
        - 关闭page/context/browser/driver，置空相关字段。
        - 捕获并吞掉所有异常，保证清理流程不中断。
        - 标记isClose为True。
        """
        try:
            if getattr(self, "page", None):
                try:
                    self.page.close()
                except Exception:
                    pass
                self.page = None
            if getattr(self, "context", None):
                try:
                    self.context.close()
                except Exception:
                    pass
                self.context = None
            if getattr(self, "browser", None):
                try:
                    self.browser.close()
                except Exception:
                    pass
                self.browser = None
            if getattr(self, "driver", None):
                try:
                    self.driver.stop()
                except Exception:
                    pass
                self.driver = None
            self._driver_thread_id = None
            self.isClose = True
        except Exception:
            # 故意吞掉异常，保证清理流程不中断
            self.isClose = True

    def cleanup(self):
        """清理所有资源，线程安全且可重入"""
        try:
            with self._lock:
                self._unsafe_cleanup_locked()
        except Exception as e:
            pass

    def dict_to_json(self, data_dict):
        """将字典转换为格式化JSON字符串"""
        try:
            return json.dumps(data_dict, ensure_ascii=False, indent=2)
        except (TypeError, ValueError) as e:
            logger.info(f"字典转JSON失败: {e}")
            return ""


def get_realistic_user_agent(mobile_mode: bool = False) -> str:
    """UA 公共辅助函数。

    目的：
    - 对外提供稳定的 User-Agent 生成接口。
    - 避免其他模块跨层调用私有方法 `_get_realistic_user_agent`。

    注意：
    - 该函数应当是纯函数（无 I/O、无副作用）。
    """
    try:
        return PlaywrightController()._get_realistic_user_agent(mobile_mode=mobile_mode)
    except Exception:
        # 最小兜底，避免调用方因 UA 生成异常而失败
        return "Mozilla/5.0"


ControlDriver = PlaywrightController()
