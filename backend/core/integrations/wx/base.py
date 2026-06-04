import requests
import json
import re
import os
from core.common.log import logger
import random

from dataclasses import dataclass
from typing import Any, Callable, Optional


_FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
]


@dataclass
class WxGatherHooks:
    """WxGather 的副作用钩子（由编排层注入）。

    目标：
    - core.wx 作为采集库，不直接依赖 DB/通知/队列等外部基础设施。
    - 由调用方注入 hooks，在关键节点触发副作用。

    约定：
    - hooks 均为 best-effort：内部自行捕获异常，不向上传播。
    """
    on_update_mps: Optional[Callable[[str, dict], None]] = None
    on_over: Optional[Callable[[list, Optional[str]], None]] = None
    on_error: Optional[Callable[[str, Optional[str], dict], None]] = None


# 定义基类
class WxGather:

    def __init__(self, is_add: bool = False, hooks: WxGatherHooks | None = None):
        self.articles: list = []
        self.aids: set[str] = set()
        self.is_add = is_add

        self.session = requests.Session()
        # requests 不支持给 Session 设置默认 timeout；统一在请求处显式传 timeout
        self._timeout = (5, 10)

        # hooks：外部副作用（DB/通知/队列/清会话等）由编排层注入
        self.hooks: WxGatherHooks | None = hooks
        if self.hooks is None:
            # 默认 hooks 放在 core.common.task.wx_hooks，避免 base 直接依赖基础设施实现
            try:
                from core.common.task.wx_hooks import build_wx_gather_hooks

                self.hooks = build_wx_gather_hooks()
            except Exception:
                self.hooks = None

        self.ensure_http_context()

    def _load_persisted_token(self) -> str:
        """best-effort: 从持久化会话读取 token。"""
        try:
            from driver.session.store import Store

            sess = Store.load_session()
            if isinstance(sess, dict):
                token = sess.get("token")
                logger.info(
                    f"[wx-token-debug] persisted_token_exists={bool(token)} updated_at={sess.get('updated_at')}"
                )
                if token:
                    return str(token)
        except Exception:
            pass
        return ""

    def all_count(self):
        if getattr(self, "articles", None) is not None:
            return len(self.articles)
        return 0

    def RecordAid(self, aid: str):
        # 使用 set 去重，避免线性查找
        if aid is not None:
            self.aids.add(str(aid))

    def HasGathered(self, aid: str):
        key = str(aid)
        if key in self.aids:
            return True
        self.aids.add(key)
        return False

    def query_existing_article_ids(self, aids: list[str]) -> set[str]:
        """批量查询数据库中已存在的文章 ID。"""
        ids = sorted({str(aid).strip() for aid in (aids or []) if str(aid).strip()})
        if not ids:
            return set()
        try:
            from core.articles import article_repo

            rows = article_repo.sync_get_articles(
                filters={"id": {"in": ids}},
                limit=len(ids),
            )
            return {str((row or {}).get("id")) for row in (rows or []) if (row or {}).get("id")}
        except Exception as e:
            logger.warning(f"查询已存在文章失败，回退为不跳过: {e}")
            return set()

    def _derive_mp_token_from_cookies(
        self, cookies: str, headers: dict | None = None
    ) -> str:
        """best-effort: 仅基于 cookies 推导 mp.weixin.qq.com 的 token。

        说明：
        - 旧版 mp 后台接口（如 /cgi-bin/searchbiz）需要 URL 参数 token。
        - 当前工程会话以 cookies 为唯一可靠依据，token 不再持久化。
        - 推导失败返回空字符串，由调用方决定是否提示重新扫码登录。
        """
        if not cookies:
            return ""

        h = (headers or {}).copy()
        h.setdefault("Cookie", cookies)
        h.setdefault("User-Agent", getattr(self, "user_agent", "") or random.choice(_FALLBACK_USER_AGENTS))

        try:
            # 访问后台首页，让服务端完成跳转并尽量在 URL 中暴露 token
            url = "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN"
            r = self.session.get(
                url, headers=h, allow_redirects=True, timeout=self._timeout
            )
            r.raise_for_status()

            final_url = getattr(r, "url", "") or ""
            m = re.search(r"[?&]token=([^&]+)", final_url)
            if m:
                return m.group(1)

            html = getattr(r, "text", "") or ""
            if "当前环境异常，完成验证后即可继续访问" in html:
                logger.info("当前环境异常，完成验证后即可继续访问")
                return ""
            # 常见：token=xxxx
            m = re.search(r"[?&]token=([^&\"']+)", html)
            if m:
                return m.group(1)
            # 退一步：token:"xxxx" 或 token = "xxxx"
            m = re.search(r"token\s*[:=]\s*['\"]([^'\"]+)['\"]", html)
            if m:
                return m.group(1)
            # 兼容 cgiData/全局对象里的 token
            m = re.search(r"cgiData[^\\n]*token\s*[:=]\s*['\"]([^'\"]+)['\"]", html)
            if m:
                return m.group(1)
            logger.warning(
                f"[wx-token-debug] derive_failed final_url={final_url[:200]} html_len={len(html)}"
            )
        except Exception as e:
            logger.error(f"_derive_mp_token_from_cookies 失败: {e}")
            return ""

        return ""

    def ensure_http_context(self, force_refresh: bool = False) -> None:
        """确保 HTTP 请求上下文已初始化（Cookie + UA + base headers）。

        说明：
        - Cookie 来源：driver.wx.service.get_cookie_header()（唯一出口）。
        - UA 来源：driver.browser.playwright.get_realistic_user_agent()（公开接口）。
        - 不在此处派生 mp token。
        """
        if (not force_refresh) and getattr(self, "headers", None) and getattr(self, "cookies", None) and getattr(self, "user_agent", None):
            return

        self.Gather_Content = os.getenv("GATHER_CONTENT", "false").lower() in ("1", "true", "yes")

        # 1) Cookie header（唯一出口）
        cookies = ""
        try:
            from driver.wx.service import get_cookie_header

            env = get_cookie_header()
            if isinstance(env, dict) and env.get("ok"):
                s = env.get("data")
                cookies = str(s) if s else ""
        except Exception:
            cookies = ""

        # 2) User-Agent（公开接口）
        ua = ""
        try:
            from driver.browser.playwright import get_realistic_user_agent

            ua = str(get_realistic_user_agent(mobile_mode=False) or "")
        except Exception:
            ua = ""
        if not ua:
            ua = random.choice(_FALLBACK_USER_AGENTS) if _FALLBACK_USER_AGENTS else "Mozilla/5.0"

        self.cookies = cookies
        self.user_agent = ua
        self.headers = {
            "Cookie": self.cookies,
            "User-Agent": self.user_agent,
        }

        # token 优先读内存/持久化会话，缺失时按需推导
        if not hasattr(self, "token"):
            self.token = ""

    def ensure_mp_token(self) -> str:
        """确保 mp token 可用（仅在需要 token 的接口里调用）。"""
        token = getattr(self, "token", "") or ""
        if token:
            logger.info("[wx-token-debug] token_source=memory")
            return token
        token = self._load_persisted_token()
        if token:
            self.token = token
            logger.info("[wx-token-debug] token_source=persisted")
            return token
        self.ensure_http_context()
        token = self._derive_mp_token_from_cookies(self.cookies, headers=self.headers)
        self.token = token
        logger.info(f"[wx-token-debug] token_source=derived success={bool(token)}")
        return token

    def require_mp_token(self) -> str:
        """获取可用 mp token，并区分未登录与风控/环境异常。"""
        self.ensure_http_context(force_refresh=True)
        if not self.cookies:
            self.Error("请先扫码登录公众号平台")
            return ""

        token = self.ensure_mp_token()
        if token:
            return token

        self.Error("登录态异常，请在公众号平台完成验证后重试")
        return ""

    def fix_header(self, url):
        # 确保基础上下文已初始化
        self.ensure_http_context()

        headers = self.headers.copy()
        headers.update(
            {
                "Referer": url,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }
        )
        return headers

    def content_extract(self, url):
        text = ""
        session = self.session
        headers = self.fix_header(url)
        try:
            r = session.get(url, headers=headers, timeout=self._timeout)
            r.raise_for_status()
            text = r.text
            text = self.remove_common_html_elements(text)
            if "当前环境异常，完成验证后即可继续访问" in text:
                logger.error("当前环境异常，完成验证后即可继续访问")
                return ""
            return text
        except Exception as e:
            logger.error(f"content_extract 请求失败: {e}")
            return ""

    def FillBack(self, CallBack=None, data=None, Ext_Data=None):
        if CallBack is not None:
            if data is not None:
                from datetime import datetime

                art = {
                    "id": str(data["id"]),
                    "wechat_account_id": data["wechat_account_id"],
                    "title": data["title"],
                    "url": data["link"],
                    "pic_url": data["cover"],
                    "content": data.get("content", ""),
                    "publish_time": data["update_time"],
                }
                if "digest" in data:
                    art["description"] = data["digest"]
                if CallBack(art):
                    art["ext"] = Ext_Data
                    # art.pop("content")
                    self.articles.append(art)

    # 通过公众号码平台接口查询公众号
    def search_Biz(self, kw: str = "", limit=10, offset=0):

        self.ensure_http_context(force_refresh=True)

        url = "https://mp.weixin.qq.com/cgi-bin/searchbiz"
        params = {
            "action": "search_biz",
            "begin": offset,
            "count": limit,
            "query": kw,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
        }
        headers = self.fix_header(url)
        token = self.require_mp_token()
        if not token:
            return
        params["token"] = token
        data = {}
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.text
            msg = json.loads(data)
            if msg["base_resp"]["ret"] == 200013:
                self.Error("frequencey control, stop at {}".format(str(kw)))
                return
            if msg["base_resp"]["ret"] != 0:
                self.Error(
                    "错误原因:{}:代码:{}".format(
                        msg["base_resp"]["err_msg"], msg["base_resp"]["ret"]
                    ),
                    code="Invalid Session",
                )
                return
        except Exception as e:
            logger.error(f"请求失败: {e}")
            raise e
        return msg

    def Start(self, wechat_account_id=None):
        self.articles = []
        # 仅初始化 cookies + headers；token 不在此处推导
        self.ensure_http_context(force_refresh=True)
        if not self.cookies:
            self.Error("请先扫码登录公众号平台")
            return
        import time

        self.update_mps(
            wechat_account_id,
            {
                "sync_time": int(time.time()),
                "update_time": int(time.time()),
            },
        )

    def Item_Over(self, item=None, CallBack=None):
        # 仅保留回调机制，避免在库层输出噪声日志
        if CallBack is not None:
            CallBack(item)

    def Error(self, error: str, code=None):
        """错误处理。

        - 副作用（清会话/通知/清队列等）交由 hooks.on_error 处理。
        - 对于 "Invalid Session"：保持历史行为，不抛异常，便于调用方优雅退出。
        - 其他错误：抛出异常。
        """
        try:
            if self.hooks and self.hooks.on_error:
                self.hooks.on_error(
                    error,
                    code,
                    {
                        "wechat_account_id": None,
                        "has_cookies": bool(getattr(self, "cookies", "")),
                        "has_token": bool(getattr(self, "token", "")),
                    },
                )
        except Exception:
            pass

        if code == "Invalid Session":
            logger.error(error)
            return

        raise Exception(error)

    def Over(self, CallBack=None):
        """抓取结束收尾。

        - 清缓存/持久化等副作用交由 hooks.on_over。
        - 保留 CallBack 兼容外部旧调用。
        """
        wechat_account_id: str | None = None
        try:
            if getattr(self, "articles", None):
                wechat_account_id = self.articles[0].get("wechat_account_id")
        except Exception:
            wechat_account_id = None

        try:
            if self.hooks and self.hooks.on_over:
                self.hooks.on_over(self.articles or [], wechat_account_id)
        except Exception:
            pass

        if CallBack is not None:
            CallBack(self.articles)

    def dateformat(self, timestamp: Any):
        from datetime import datetime, timezone

        # UTC时间对象
        utc_dt = datetime.fromtimestamp(int(timestamp), timezone.utc)
        t = utc_dt.strftime("%Y-%m-%d %H:%M:%S")

        # UTC转本地时区
        local_dt = utc_dt.astimezone()
        t = local_dt.strftime("%Y-%m-%d %H:%M:%S")
        return t

    def remove_html_region(self, html_content: str, patterns: list) -> str:
        """
        使用正则表达式移除HTML中指定的区域内容

        Args:
            html_content: 原始HTML内容
            patterns: 正则表达式模式列表，用于匹配需要移除的区域

        Returns:
            处理后的HTML内容
        """
        if not html_content or not patterns:
            return html_content

        processed_content = html_content

        for pattern in patterns:
            try:
                # 使用正则表达式移除匹配的区域
                processed_content = re.sub(
                    pattern, "", processed_content, flags=re.DOTALL | re.IGNORECASE
                )
            except re.error as e:
                logger.error(f"正则表达式错误: {pattern}, 错误信息: {e}")
                continue
            except Exception as e:
                logger.error(f"处理HTML区域时发生错误: {e}")
                continue

        return processed_content

    def _clean_article_content(self, html_content: str) -> str:
        """轻量清洗 HTML（替代对 driver.wx.article.Web.clean_article_content 的依赖）。

        目标：
        - 移除 head/script/style/link/meta 等常见非正文元素，减少后续正则误伤。
        - 仅做 best-effort 处理；失败则返回原文。

        说明：
        - 这里不引入 Playwright/driver 依赖，避免核心采集流程与 driver 层耦合。
        """
        if not html_content:
            return html_content

        try:
            # 先移除 head 整段（包含 meta/link/script/style 等）
            cleaned = re.sub(
                r"<head[^>]*>.*?</head>",
                "",
                html_content,
                flags=re.DOTALL | re.IGNORECASE,
            )

            # 再移除常见无关公众号分组
            cleaned = re.sub(
                r"<script[^>]*>.*?</script>",
                "",
                cleaned,
                flags=re.DOTALL | re.IGNORECASE,
            )
            cleaned = re.sub(
                r"<style[^>]*>.*?</style>", "", cleaned, flags=re.DOTALL | re.IGNORECASE
            )
            cleaned = re.sub(
                r"<link[^>]*?>", "", cleaned, flags=re.DOTALL | re.IGNORECASE
            )
            cleaned = re.sub(
                r"<meta[^>]*?>", "", cleaned, flags=re.DOTALL | re.IGNORECASE
            )
            return cleaned
        except Exception:
            return html_content

    def remove_common_html_elements(self, html_content: str) -> str:
        """
        移除常见的HTML元素区域

        Args:
            html_content: 原始HTML内容

        Returns:
            处理后的HTML内容
        """
        if not html_content:
            return html_content

        # 常见的需要移除的HTML元素模式
        common_patterns = [
            # 移除script公众号分组及其内容
            r"<script[^>]*>.*?</script>",
            # 移除style公众号分组及其内容
            r"<style[^>]*>.*?</style>",
            # 移除注释
            r"<!--.*?-->",
            # 移除iframe公众号分组
            r"<iframe[^>]*>.*?</iframe>",
            # 移除noscript公众号分组
            r"<noscript[^>]*>.*?</noscript>",
            # 移除广告相关的div（包含特定class或id）
            r'<div[^>]*(?:class|id)=["\'][^"\']*(?:ad|advertisement|banner)[^"\']*["\'][^>]*>.*?</div>',
            # 移除header区域
            r"<header[^>]*>.*?</header>",
            # 移除footer区域
            r"<footer[^>]*>.*?</footer>",
            # 移除nav区域
            r"<nav[^>]*>.*?</nav>",
            # 移除aside区域
            r"<aside[^>]*>.*?</aside>",
        ]
        html_content = self._clean_article_content(html_content)
        return self.remove_html_region(html_content, common_patterns)

    def update_mps(self, wechat_account_id: str, mp: dict):
        """更新公众号同步状态/时间（副作用由 hooks 实现）。"""
        try:
            if self.hooks and self.hooks.on_update_mps:
                self.hooks.on_update_mps(wechat_account_id, mp)
        except Exception:
            pass
