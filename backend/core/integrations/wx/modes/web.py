from __future__ import annotations

import json
import random
import re
import time

import requests
from bs4 import BeautifulSoup

from core.articles.collection_policy import (
    ExistingArticleAction,
    classify_article_collection_decision,
    cutoff_timestamp,
    is_older_than_cutoff,
)
from core.common.log import logger
from core.integrations.wx.base import WxGather, wechat_error_code


class WechatAccountWeb(WxGather):
    """公众号文章抓取（Web 浏览器模式）。

    特点：
    - 列表拉取沿用 /cgi-bin/appmsgpublish（分页 JSON）。
    - 正文抓取委托给 driver.wx.service.fetch_article（Playwright 侧），提升通过率。

    依赖：
    - 父类 WxGather：Start()/fix_header()/session/回调与错误处理。
        - driver.wx.service.fetch_article：统一出口的文章抓取能力。
    """

    def __init__(self, is_add: bool = False, hooks=None):
        # hooks 由编排层注入；不传时由 WxGather 负责加载默认 hooks
        super().__init__(is_add=is_add, hooks=hooks)

    def content_extract(self, url: str) -> str:
        """通过 wx_service.fetch_article 抓取文章正文 HTML，并做清洗。"""
        try:
            # 正文抓取走 driver 统一出口（Playwright）
            from driver.wx.service import fetch_article

            env = fetch_article(url)
            if not env or not env.get("ok"):
                # 失败时保持原行为：记录错误并返回空串
                err = (env or {}).get("error") or {}
                msg = err.get("message") or "fetch_article failed"
                reason = err.get("reason")
                logger.error(f"{msg}: {reason}" if reason else msg)
                return ""

            r = env.get("data") or {}
            text = r.get("content", "")
            if not text:
                return ""

            # 清理公共/无关 HTML 元素（父类工具方法）
            text = self.remove_common_html_elements(text)
            if not text:
                return ""

            # 环境异常提示：需要人机验证/风控拦截
            if "当前环境异常，完成验证后即可继续访问" in text:
                logger.error("当前环境异常，完成验证后即可继续访问")
                return ""

            soup = BeautifulSoup(text, "html.parser")

            # 兼容历史行为：此处使用整页 soup 作为内容容器
            js_content_div = soup
            if js_content_div is None:
                return ""

            # 移除 style，避免隐藏
            js_content_div.attrs.pop("style", None)

            # 处理正文内图片公众号分组：data-src → src，并统一宽度
            img_tags = js_content_div.find_all("img")
            for img_tag in img_tags:
                if "data-src" in img_tag.attrs:
                    img_tag["src"] = img_tag["data-src"]
                    del img_tag["data-src"]
                if "style" in img_tag.attrs:
                    style = img_tag["style"]
                    style = re.sub(r"width\s*:\s*\d+\s*px", "width: 1080px", style)
                    img_tag["style"] = style

            return js_content_div.prettify()
        except Exception as e:
            logger.error(e)
            return ""

    def get_Articles(
        self,
        faker_id: str = None,
        wechat_account_id: str = None,
        wechat_account_name: str = "",
        CallBack=None,
        start_page: int = 0,
        MaxPage: int = 1,
        interval: int = 10,
        Gather_Content: bool = False,
        Item_Over_CallBack=None,
        Over_CallBack=None,
        MaxArticleAgeDays: int = 7,
        RepairFailedExisting: bool = True,
    ):
        """分页拉取公众号发布列表（/cgi-bin/appmsgpublish），可选抓取正文。"""

        # 初始化会话上下文（cookie/UA/headers/session），不在此处派生 token
        self.Start(wechat_account_id=wechat_account_id)

        # 允许通过父类开关覆盖
        if getattr(self, "Gather_Content", False):
            Gather_Content = True

        logger.info(f"Web浏览器模式,是否采集[{wechat_account_name}]内容：{Gather_Content}")

        url = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
        session = self.session

        count = 5
        i = int(start_page or 0)
        cutoff_ts = cutoff_timestamp(MaxArticleAgeDays)

        # token 仅对需要 token 的接口按需推导
        token = self.require_mp_token()
        if not token:
            return

        while True:
            if i >= int(MaxPage or 0):
                break

            begin = i * count
            page_candidates = 0
            page_skip_existing = 0
            page_skip_old = 0
            page_processed = 0
            page_recent_candidates = 0

            params = {
                "sub": "list",
                "sub_action": "list_ex",
                "begin": str(begin),
                "count": count,
                "fakeid": faker_id,
                "token": token,
                "lang": "zh_CN",
                "f": "json",
                "ajax": 1,
            }

            # 随机 sleep 降频
            try:
                time.sleep(random.randint(0, max(0, int(interval or 0))))
            except Exception:
                pass

            try:
                headers = self.fix_header(url)
                resp = session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                self._sync_cookie_header_from_session()
                msg = resp.json()

                base_resp = msg.get("base_resp") or {}
                ret = base_resp.get("ret")

                # 200013：频控
                if ret == 200013:
                    self.Error(f"frequencey control, stop at {begin}")
                    return

                # 仅 200003 表示会话失效；其他非 0 返回只影响当前任务
                if ret != 0:
                    err_msg = base_resp.get("err_msg", "")
                    self.Error(
                        f"错误原因:{err_msg}:代码:{ret}",
                        code=wechat_error_code(ret),
                    )
                    return

                publish_page = msg.get("publish_page")
                if not publish_page:
                    # 没有 publish_page：视为结束
                    break

                if isinstance(publish_page, str):
                    publish_page = json.loads(publish_page)

                publish_list = (publish_page or {}).get("publish_list") or []
                if not publish_list:
                    break

                for pub in publish_list:
                    publish_info = pub.get("publish_info")
                    if not publish_info:
                        continue

                    try:
                        if isinstance(publish_info, str):
                            publish_info = json.loads(publish_info)
                    except Exception:
                        continue

                    appmsgex = (publish_info or {}).get("appmsgex") or []
                    existing_articles = super().query_existing_articles(
                        [str((it or {}).get("aid") or "") for it in appmsgex]
                    )
                    for item in appmsgex:
                        try:
                            aid = str(item.get("aid") or "").strip()
                            if not aid:
                                continue
                            page_candidates += 1
                            is_old = is_older_than_cutoff(item, cutoff_ts)
                            if not is_old:
                                page_recent_candidates += 1
                            action = classify_article_collection_decision(
                                item,
                                existing_article=existing_articles.get(aid),
                                cutoff_ts=cutoff_ts,
                                repair_failed_existing=RepairFailedExisting,
                            )
                            if action == ExistingArticleAction.SKIP:
                                if is_old:
                                    page_skip_old += 1
                                else:
                                    page_skip_existing += 1
                                continue

                            if Gather_Content and aid and (not super().HasGathered(aid)):
                                link = item.get("link") or ""
                                item["content"] = self.content_extract(link) if link else ""
                            else:
                                item["content"] = ""

                            item["id"] = item.get("aid")
                            item["wechat_account_id"] = wechat_account_id

                            if CallBack is not None:
                                super().FillBack(
                                    CallBack=CallBack,
                                    data=item,
                                    Ext_Data={
                                        "mp_title": wechat_account_name,
                                        "wechat_account_id": wechat_account_id,
                                    },
                                )
                                page_processed += 1
                        except Exception:
                            continue

                logger.info(
                    f"[dedup-debug] mode=web wechat_account_id={wechat_account_id} page={i} "
                    f"candidates={page_candidates} recent={page_recent_candidates} "
                    f"skip_old={page_skip_old} skip_existing={page_skip_existing} "
                    f"processed={page_processed} gather_content={Gather_Content}"
                )
                if page_candidates > 0 and page_recent_candidates == 0:
                    logger.info(
                        f"[collection-policy] stop old page mode=web "
                        f"wechat_account_id={wechat_account_id} page={i}"
                    )
                    break
                i += 1

            except requests.exceptions.Timeout:
                logger.error("Request timed out")
                return
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {e}")
                return
            finally:
                super().Item_Over(
                    item={"wechat_account_id": wechat_account_id, "wechat_account_name": wechat_account_name},
                    CallBack=Item_Over_CallBack,
                )

        super().Over(CallBack=Over_CallBack)
        return self.articles
