from driver.browser.playwright import PlaywrightController
from typing import Any, List, Optional
from core.common.log import logger
import time
import base64
import re
from datetime import datetime
from driver.session.manager import SessionManager
from driver.wx.schemas import WxMpSession, WxMpInfo, WxArticleInfo, WxArticleError


class WXArticleFetcher:
    """微信公众号文章获取器"""

    def __init__(self, wait_timeout: int = 10000):
        """初始化文章获取器"""
        self.wait_timeout = wait_timeout
        self.controller = PlaywrightController()
        if not self.controller:
            raise Exception("WebDriver未初始化或未登录")
        # 会话管理：统一从 Store/SessionManager 读取公众号登录态
        self._session: SessionManager = SessionManager()

    def convert_publish_time_to_timestamp(self, publish_time_str: str) -> int:
        """将发布时间字符串转换为时间戳"""
        try:
            formats = [
                "%Y-%m-%d %H:%M:%S",  # 2024-01-01 12:30:45
                "%Y年%m月%d日 %H:%M",  # 2024年03月24日 17:14
                "%Y-%m-%d %H:%M",  # 2024-01-01 12:30
                "%Y-%m-%d",  # 2024-01-01
                "%Y年%m月%d日",  # 2024年01月01日
                "%m月%d日",  # 01月01日 (当年)
            ]

            for fmt in formats:
                try:
                    if fmt == "%m月%d日":
                        current_date = datetime.now()
                        current_year = current_date.year
                        full_time_str = f"{current_year}年{publish_time_str}"
                        dt = datetime.strptime(full_time_str, "%Y年%m月%d日")
                        if dt > current_date:
                            dt = dt.replace(year=current_year - 1)
                    else:
                        dt = datetime.strptime(publish_time_str, fmt)
                    return int(dt.timestamp())
                except ValueError:
                    continue

            # 如果所有格式都失败，返回当前时间戳
            logger.warning(f"无法解析时间格式: {publish_time_str}，使用当前时间")
            return int(datetime.now().timestamp())

        except Exception as e:
            logger.error(f"时间转换失败: {e}")
            return int(datetime.now().timestamp())

    def extract_biz_from_source(self, url: str, page=None) -> str:
        """从URL或页面源码中提取biz参数

        Args:
            url: 文章URL
            page: Playwright Page实例，可选

        Returns:
            biz参数值
        """
        # 尝试从URL中提取
        match = re.search(r"[?&]__biz=([^&]+)", url)
        if match:
            return match.group(1)

        # 从页面源码中提取（需要page参数）
        if page is None:
            if not hasattr(self, "page") or self.page is None:
                return ""
            page = self.page

        try:
            # 从页面源码中查找biz信息
            page_source = page.content()
            logger.info(f"开始解析Biz")
            biz_match = re.search(r'var biz = "([^"]+)"', page_source)
            if biz_match:
                return biz_match.group(1)

            # 尝试其他可能的biz存储位置
            biz_match = re.search(r"window\.__biz=([^&]+)", page_source)
            if biz_match:
                return biz_match.group(1)
            # biz_match=page.evaluate('() =>window.biz')
            return ""

        except Exception as e:
            logger.error(f"从页面源码中提取biz参数失败: {e}")
            return ""

    def extract_id_from_url(self, url: str) -> str:
        """从微信文章URL中提取ID

        Args:
            url: 文章URL

        Returns:
            文章ID字符串, 如果提取失败返回None
        """
        try:
            # 从URL中提取ID部分
            match = re.search(r"/s/([A-Za-z0-9_-]+)", url)
            if not match:
                return ""

            id_str = match.group(1)

            # 尝试按 base64 解码（部分短链会将真实 ID 编码在 path 中）
            # 注意：不要在解码失败时返回“追加了 padding 的字符串”，否则会污染原始 ID
            padded = id_str
            padding = (-len(padded)) % 4
            if padding:
                padded = padded + ("=" * padding)

            try:
                id_number = base64.b64decode(padded).decode("utf-8")
                return id_number
            except Exception:
                # 解码失败则回退为原始 path 片段
                return id_str

        except Exception as e:
            logger.error(f"提取文章ID失败: {e}")
            return ""

    def _inject_mp_cookies(self):
        """向浏览器上下文注入已保存的公众号 Cookie"""
        try:
            persisted: Optional[WxMpSession] = self._session.load_persisted_session()
            # persisted 为 WxMpSession | None
            if not persisted:
                return

            # 1) 优先使用 Playwright cookies 列表格式
            cookies = persisted.get("cookies") if persisted else None
            cookie_list = self._session.normalize_cookie_list(cookies or [])
            if cookie_list:
                self.controller.add_cookies(cookie_list)
                return

            # 2) 退化：解析 cookies_str（形如 a=b; c=d）
            cookies_str = str(persisted.get("cookies_str", "") or "")
            if not cookies_str:
                return

            pairs = [kv.strip() for kv in cookies_str.split(";") if kv.strip()]
            parsed: List[dict] = []
            for kv in pairs:
                if "=" not in kv:
                    continue
                name, value = kv.split("=", 1)
                name = name.strip()
                value = value.strip()
                if not name:
                    continue
                parsed.append(
                    {
                        "name": name,
                        "value": value,
                        # Playwright 允许用 url 快速指定 domain 范围
                        "url": "https://mp.weixin.qq.com",
                    }
                )

            if parsed:
                self.controller.add_cookies(parsed)
        except Exception:
            # 注入失败属于可接受降级
            return

    def FixArticle(self, urls: list | None = None, wechat_account_id: str = "") -> bool:
        """批量修复文章内容"""
        try:
            from jobs.article import UpdateArticle

            # 设置默认URL列表
            if not urls:
                urls = ["https://mp.weixin.qq.com/s/YTHUfxzWCjSRnfElEkL2Xg"]

            success_count = 0
            total_count = len(urls)

            for i, url in enumerate(urls, 1):
                if url == "":
                    continue
                logger.info(f"正在处理第 {i}/{total_count} 篇文章: {url}")

                try:
                    article_data = self.get_article_content(url)

                    # 构建文章数据
                    article = {
                        "id": article_data.get("id"),
                        "title": article_data.get("title"),
                        # 若显式传入 wechat_account_id，则覆盖；否则使用抓取结果中的 wechat_account_id
                        "wechat_account_id": wechat_account_id or article_data.get("wechat_account_id"),
                        "publish_time": article_data.get("publish_time"),
                        "pic_url": article_data.get("pic_url"),
                        "content": article_data.get("content"),
                        "url": url,
                    }

                    # 删除content字段避免重复存储
                    content_backup = article_data.get("content", "")
                    del article_data["content"]

                    logger.success(f"获取成功: {article_data}")

                    # 更新文章
                    ok = UpdateArticle(article, check_exist=True)
                    if ok:
                        success_count += 1
                        logger.info(
                            f"已更新文章: {article_data.get('title', '未知标题')}"
                        )
                    else:
                        logger.warning(
                            f"更新失败: {article_data.get('title', '未知标题')}"
                        )

                    # 恢复content字段
                    article_data["content"] = content_backup

                    # 避免请求过快，但只在非最后一个请求时等待
                    if i < total_count:
                        time.sleep(3)

                except Exception as e:
                    logger.error(f"处理文章失败 {url}: {e}")
                    continue

            logger.success(f"批量处理完成: 成功 {success_count}/{total_count}")
            return success_count > 0

        except Exception as e:
            logger.error(f"批量修复文章失败: {e}")
            return False
        finally:
            self.Close()

    def get_article_content(self, url: str) -> WxArticleInfo:
        """获取单篇文章详细内容"""
        info: WxArticleInfo = {
            "id": self.extract_id_from_url(url),
            "title": "",
            "publish_time": "",
            "content": "",
            "images": [],
            "mp_info": WxMpInfo(mp_name="", logo="", biz=""),
        }
        self.controller.start_browser(mobile_mode=True, dis_image=False)

        # 注入已保存的 Cookie（best-effort）
        self._inject_mp_cookies()

        self.page = self.controller.page
        logger.warning(f"Get:{url} Wait:{self.wait_timeout}")
        self.controller.open_url(url, wait_until="load")
        page = self.page
        content = ""
        body = ""

        # 无论成功失败都要收尾关闭浏览器，避免长期占用资源
        try:
            # 解析正文/元信息（容错优先）
            try:
                page.wait_for_load_state("load", timeout=self.wait_timeout)
                # 优先等待正文容器出现
                try:
                    page.wait_for_selector(
                        "#js_content, #js_article, body", timeout=self.wait_timeout
                    )
                except Exception:
                    pass
                body = (page.locator("body").text_content() or "").strip()
                info["content"] = body
                if "当前环境异常，完成验证后即可继续访问" in body:
                    info["content"] = ""
                    self.controller.cleanup()
                    time.sleep(5)
                    raise WxArticleError(
                        code="WX_ENV_BLOCKED",
                        message="environment blocked",
                        reason="当前环境异常，完成验证后即可继续访问",
                        retryable=False,
                    )
                if (
                    "该内容已被发布者删除" in body
                    or "The content has been deleted by the author." in body
                ):
                    info["content"] = "DELETED"
                    raise WxArticleError(
                        code="WX_ARTICLE_DELETED",
                        message="article deleted",
                        reason="该内容已被发布者删除",
                        retryable=False,
                    )
                if "内容审核中" in body:
                    info["content"] = "DELETED"
                    raise WxArticleError(
                        code="WX_ARTICLE_RESTRICTED",
                        message="article restricted",
                        reason="内容审核中",
                        retryable=False,
                    )
                if "该内容暂时无法查看" in body:
                    info["content"] = "DELETED"
                    raise WxArticleError(
                        code="WX_ARTICLE_RESTRICTED",
                        message="article restricted",
                        reason="该内容暂时无法查看",
                        retryable=False,
                    )
                if "违规无法查看" in body:
                    info["content"] = "DELETED"
                    raise WxArticleError(
                        code="WX_ARTICLE_RESTRICTED",
                        message="article restricted",
                        reason="违规无法查看",
                        retryable=False,
                    )
                if "发送失败无法查看" in body:
                    info["content"] = "DELETED"
                    raise WxArticleError(
                        code="WX_ARTICLE_RESTRICTED",
                        message="article restricted",
                        reason="发送失败无法查看",
                        retryable=False,
                    )
                if "Unable to view this content because it violates regulation" in body:
                    info["content"] = "DELETED"
                    raise WxArticleError(
                        code="WX_ARTICLE_RESTRICTED",
                        message="article restricted",
                        reason="违规无法查看",
                        retryable=False,
                    )

                # 获取标题/描述/题图（容错）
                title = (
                    page.locator('meta[property="og:title"]').get_attribute("content")
                    or ""
                )
                description = (
                    page.locator('meta[property="og:description"]').get_attribute(
                        "content"
                    )
                    or ""
                )
                topic_image = (
                    page.locator('meta[property="twitter:image"]').get_attribute(
                        "content"
                    )
                    or ""
                )

                if not title:
                    title = page.evaluate("() => document.title") or ""

                # 获取正文内容和图片
                content_element = page.locator("#js_content")
                content = content_element.inner_html()

                # 获取图集内容
                if content == "":
                    content_element = page.locator("#js_article")
                    content = content_element.inner_html()
                    content = self.clean_article_content(str(content))

                # 获取图像资源
                images = []
                try:
                    img_locs = content_element.locator("img").all()
                    for img in img_locs:
                        src = img.get_attribute("data-src") or img.get_attribute("src")
                        if src:
                            images.append(src)
                except Exception as _img_err:
                    logger.warning(f"提取图片失败: {_img_err}")

                if images:
                    info["pic_url"] = images[0]

                # 获取发布时间
                try:
                    pub_loc = page.locator("#publish_time")
                    pub_loc.wait_for(state="visible", timeout=2000)
                    publish_time_str = (pub_loc.inner_text() or "").strip()
                    publish_time = self.convert_publish_time_to_timestamp(
                        publish_time_str
                    )
                except Exception as e:
                    logger.warning(f"获取发布时间失败: {e}")
                    publish_time = ""
                info["title"] = title
                info["publish_time"] = publish_time
                info["content"] = content
                info["images"] = images
                info["description"] = description
                info["topic_image"] = topic_image

            except Exception as e:
                logger.error(f"文章内容获取失败: {str(e)}")
                preview = (body or "")[:200]
                if not preview:
                    try:
                        preview = (page.content() or "")[:200]
                    except Exception:
                        preview = ""
                logger.warning(f"页面内容预览: {preview}...")
                msg = str(e)
                if "Timeout" in msg or "timeout" in msg or "timed out" in msg:
                    raise WxArticleError(
                        code="WX_NETWORK_TIMEOUT",
                        message="network timeout",
                        reason=msg,
                        retryable=True,
                    )
                raise

            # 等待关键元素加载
            # 使用更精确的选择器避免匹配多个元素
            ele_logo = page.locator("#js_like_profile_bar .wx_follow_avatar img")
            # 获取<img>公众号分组的src属性
            logo_src = ele_logo.get_attribute("src")

            # 获取公众号名称（避免依赖 jQuery）
            title = (
                page.locator("#js_wx_follow_nickname").text_content() or ""
            ).strip()

            # biz 可能不存在，需降级处理
            try:
                biz = page.evaluate("() => window.biz")
            except Exception:
                biz = ""

            info["mp_info"] = WxMpInfo(
                mp_name=title,
                logo=logo_src,
                biz=biz or self.extract_biz_from_source(url, page),
            )
            # wechat_account_id 以 biz 的解码值派生（失败则留空）
            try:
                if info["mp_info"].get("biz"):
                    info["wechat_account_id"] = "MP_WXS_" + base64.b64decode(
                        info["mp_info"]["biz"]
                    ).decode("utf-8")
            except Exception:
                info["wechat_account_id"] = info.get("wechat_account_id") or ""

            return info
        finally:
            self.Close()

    def Close(self):
        """关闭浏览器"""
        if hasattr(self, "controller"):
            self.controller.Close()
        else:
            logger.info("WXArticleFetcher未初始化或已销毁")

    def __del__(self):
        """销毁文章获取器"""
        try:
            if hasattr(self, "controller") and self.controller is not None:
                self.controller.Close()
        except Exception as e:
            # 析构函数中避免抛出异常
            pass

    def clean_article_content(self, html_content: str):
        from core.articles.html_tools import htmltools

        return htmltools.clean_html(
            str(html_content),
            remove_selectors=["link", "head", "script"],
            remove_attributes=[
                {"name": "style", "value": "display: none;"},
                {"name": "style", "value": "display:none;"},
                {"name": "aria-hidden", "value": "true"},
            ],
        )


# 懒加载单例：避免 import 时就启动浏览器/初始化 Playwright，减少环境副作用
_WEB_SINGLETON: Optional[WXArticleFetcher] = None


def get_web() -> WXArticleFetcher:
    """获取文章抓取器单例。

    说明：
    - 仅在首次调用时创建实例，避免模块导入阶段就触发浏览器相关初始化。
    - 需要自定义 wait_timeout 时，可在首次调用前通过 `get_web_with_timeout(...)` 获取。
    """
    global _WEB_SINGLETON
    if _WEB_SINGLETON is None:
        _WEB_SINGLETON = WXArticleFetcher()
    return _WEB_SINGLETON


def get_web_with_timeout(wait_timeout: int) -> WXArticleFetcher:
    """获取文章抓取器单例，并允许在首次创建时指定 wait_timeout。"""
    global _WEB_SINGLETON
    if _WEB_SINGLETON is None:
        _WEB_SINGLETON = WXArticleFetcher(wait_timeout=wait_timeout)
    return _WEB_SINGLETON
