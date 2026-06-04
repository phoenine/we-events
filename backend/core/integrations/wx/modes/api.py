from __future__ import annotations

import json
import random
import time
from typing import Any, Optional

from bs4 import BeautifulSoup
from core.common.log import logger
from core.integrations.wx.base import WxGather


class MpsApi(WxGather):
    """公众号文章抓取（API 获取模式）。

    继承 WxGather：
    - Start(): 初始化会话上下文（cookie/UA/headers/session），并做必要的登录态检查。
    - fix_header(): 生成 requests 请求头。
    - ensure_mp_token(): 仅在需要 token 的接口里按需推导 token。

    本类关注点：
    - 调用 /cgi-bin/appmsg 拉取文章列表。
    - 可选抓取文章详情页 HTML，并用 BeautifulSoup 提取 #js_content 正文。
    """

    def __init__(self, is_add: bool = False, hooks=None):
        # hooks 由编排层注入；不传时由 WxGather 自行尝试加载默认 hooks
        super().__init__(is_add=is_add, hooks=hooks)

    def content_extract(self, url: str) -> str:
        """抓取并解析文章正文 HTML。

        流程：
        1) 调用父类 content_extract(url) 拉取原始页面 HTML（或文本）。
        2) 使用 BeautifulSoup 解析并定位正文容器 div#js_content。
        3) 清理 style（例如移除 visibility: hidden），并修正图片：
           - data-src → src（便于直接展示）
           - 将 style 内的 width 像素值统一替换为 1080px

        返回：
        - 返回 prettify() 后的正文 HTML 字符串；失败返回空字符串。
        """
        try:
            # 由父类获取页面原始 HTML（父类内部只用 Cookie+UA，不会派生 token）
            text = super().content_extract(url)
            if not text:
                return ""

            # 解析 HTML
            soup = BeautifulSoup(text, "lxml")

            # 定位正文容器
            js_content_div = soup.find("div", id="js_content")
            if js_content_div is None:
                # 兼容：正文容器可能缺失（风控页/跳转页等）
                return ""

            # 清理 style（常见 visibility:hidden）
            try:
                style = js_content_div.get("style", "") or ""
                style = style.replace("visibility: hidden;", "").replace(
                    "visibility:hidden;", ""
                )
                if style:
                    js_content_div["style"] = style
            except Exception:
                pass

            # 处理正文内图片公众号分组：data-src -> src，并统一宽度
            try:
                img_tags = js_content_div.find_all("img")
                for img in img_tags:
                    if img.has_attr("data-src") and not img.get("src"):
                        img["src"] = img.get("data-src")
                    # 统一 style width（尽量不破坏原样式结构，只做替换）
                    if img.has_attr("style"):
                        img["style"] = (
                            img["style"]
                            .replace("width: 100%;", "width: 1080px;")
                            .replace("width:100%;", "width:1080px;")
                        )
            except Exception:
                pass

            return js_content_div.prettify()
        except Exception:
            return ""

    def get_Articles(
        self,
        faker_id: str = "",
        Mps_id: str = "",
        Mps_title: str = "",
        CallBack=None,
        start_page: int = 0,
        MaxPage: int = 999,
        interval: int = 5,
        Gather_Content: bool = False,
        Item_Over_CallBack=None,
        Over_CallBack=None,
    ):
        """分页拉取公众号文章列表，并可选抓取正文内容。

        参数说明（保留历史命名）：
        - faker_id: 公众号 fakeid（用于 appmsg 接口）
        - Mps_id: 本系统内公众号 id（透传给回调/落库）
        - Mps_title: 公众号标题（仅用于日志/回调扩展信息）
        - CallBack: 单篇文章处理回调（每条 app_msg_list item 调用一次）
        - start_page: 起始页（从 0 开始）
        - MaxPage: 最大页数（按“页”计）
        - interval: 翻页请求的随机等待上限（秒），用于降频
        - Gather_Content: 是否抓取正文（True 时会额外请求文章详情页）
        - Item_Over_CallBack: 每页/每轮结束回调（finally 中调用）
        - Over_CallBack: 全部结束回调

        流程概览：
        1) Start(wechat_account_id=...) 初始化会话上下文（cookie/UA/headers/session）。
        2) 调用 /cgi-bin/appmsg 获取文章列表（分页）。
        3) 对每条文章：按需抓取 content，并触发回调。
        4) 处理频控/会话失效等错误码并退出循环。
        """
        # 1) 初始化会话上下文（cookie/UA/headers/session），不在此处派生 token
        self.Start(wechat_account_id=Mps_id)

        # 2) appmsg 列表接口
        url = "https://mp.weixin.qq.com/cgi-bin/appmsg"
        session = self.session

        # 分页参数
        count = 5  # 每页条数（历史默认）
        i = int(start_page or 0)

        # token 仅对需要 token 的接口按需推导（appmsg 通常需要）
        token = self.require_mp_token()
        if not token:
            return

        # 遍历分页
        while i < int(MaxPage or 0):
            begin = i * count
            page_candidates = 0
            page_skip_existing = 0
            page_processed = 0

            # 随机 sleep 降频，减少触发频控概率
            try:
                time.sleep(random.randint(0, max(0, int(interval or 0))))
            except Exception:
                pass

            headers = self.fix_header(url)

            params = {
                "action": "list_ex",
                "begin": begin,
                "count": count,
                "fakeid": faker_id,
                "type": "9",
                "query": "",
                "token": token,
                "lang": "zh_CN",
                "f": "json",
                "ajax": "1",
            }

            try:
                resp = session.get(
                    url, params=params, headers=headers, timeout=self._timeout
                )
                resp.raise_for_status()
                msg = resp.json()
            except Exception as e:
                # 请求异常属于硬失败：抛出让上层感知（保持原有“异常可见”策略）
                logger.error(f"请求失败: {e}")
                raise

            # ret 码处理（与 search_Biz 逻辑一致）
            base_resp = msg.get("base_resp") or {}
            ret = base_resp.get("ret")

            # 200013：频控（frequencey control）
            if ret == 200013:
                self.Error(f"frequencey control, stop at {Mps_title or Mps_id}")
                return

            # 200003 或其他非 0：会话失效 / 异常状态
            if ret != 0:
                err_msg = base_resp.get("err_msg", "")
                self.Error(
                    f"错误原因:{err_msg}:代码:{ret}",
                    code="Invalid Session",
                )
                return

            # app_msg_list：文章列表
            items = msg.get("app_msg_list") or []
            if not items:
                # 没有更多数据：正常退出
                break

            existing_ids = self.query_existing_article_ids(
                [str((it or {}).get("aid") or "") for it in items]
            )
            try:
                for item in items:
                    try:
                        # 补齐 wechat_account_id（供回调与上层处理）
                        item["wechat_account_id"] = Mps_id

                        # 去重：防止同一文章重复采集/回调（aid/链接有时可能重复）
                        aid = str(item.get("aid") or "").strip()
                        if not aid:
                            continue
                        page_candidates += 1
                        if aid in existing_ids:
                            page_skip_existing += 1
                            continue
                        if self.HasGathered(aid):
                            continue

                        # 可选：抓取正文
                        if Gather_Content:
                            link = item.get("link") or ""
                            if link:
                                item["content"] = self.content_extract(link)

                        # 回调：由父类统一封装数据结构（art），并按回调返回值决定是否 append
                        super().FillBack(
                            CallBack=CallBack,
                            data=item,
                            Ext_Data={"mp_title": Mps_title},
                        )
                        page_processed += 1
                    except Exception:
                        # 单条失败不影响整体分页（best-effort）
                        continue
            finally:
                # 每轮结束回调：用于上层做进度/落库/清理
                super().Item_Over(item=i, CallBack=Item_Over_CallBack)

            logger.info(
                f"[dedup-debug] mode=api wechat_account_id={Mps_id} page={i} "
                f"candidates={page_candidates} skip_existing={page_skip_existing} "
                f"processed={page_processed} gather_content={Gather_Content}"
            )
            i += 1

        # 全部结束回调
        super().Over(CallBack=Over_CallBack)
        return self.articles
