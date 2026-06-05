from core.integrations.wx.base import WxGather
from core.integrations.wx.modes.api import WechatAccountApi
from core.integrations.wx.modes.app import WechatAccountAppMsg
from core.integrations.wx.modes.web import WechatAccountWeb
from core.common.runtime_settings import runtime_settings
from core.common.log import logger

__all__ = [
    "WxGather",
    "WechatAccountApi",
    "WechatAccountAppMsg",
    "WechatAccountWeb",
    "search_Biz",
    "create_gather",
]


def search_Biz(kw: str = "", limit: int = 10, offset: int = 0):
    """公众号搜索便捷入口。"""
    return WxGather().search_Biz(kw, limit=limit, offset=offset)


def create_gather(mode: str | None = None, is_add: bool = False):
    """根据配置或显式 mode 创建采集器实例。"""
    selected_mode = str(mode or runtime_settings.get_sync("gather.model", "app")).strip().lower()
    if selected_mode == "api":
        return WechatAccountApi(is_add=is_add)
    if selected_mode == "web":
        return WechatAccountWeb(is_add=is_add)
    if selected_mode == "app":
        return WechatAccountAppMsg(is_add=is_add)

    logger.warning(f"未知采集模式: {selected_mode}, 回退到 app")
    return WechatAccountAppMsg(is_add=is_add)

if __name__ == "__main__":
    pass
