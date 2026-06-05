from __future__ import annotations
from core.common.log import logger
from core.integrations.wx.base import WxGatherHooks


def build_wx_gather_hooks() -> WxGatherHooks:
    """构建 WxGather 的默认 hooks 实现。"""

    def _on_update_wechat_account(wechat_account_id: str, account: dict) -> None:
        """更新公众号同步状态/时间（DB 副作用）。"""
        try:
            from datetime import datetime, timezone
            import time
            from core.wechat_accounts import wechat_account_repo

            current_time = int(time.time())
            update_data = {
                "last_fetch": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if isinstance(account, dict):
                if account.get("update_time"):
                    try:
                        update_data["last_publish"] = datetime.fromtimestamp(
                            int(account.get("update_time")), tz=timezone.utc
                        ).isoformat()
                    except Exception:
                        pass
                if account.get("status") is not None:
                    update_data["status"] = account.get("status")

            wechat_account_repo.sync_update_wechat_account(wechat_account_id, update_data)
        except Exception:
            return

    def _on_error(error: str, code: str | None, ctx: dict) -> None:
        """错误处理副作用（仅对登录失效做处理）。"""
        if code != "Invalid Session":
            return

        # 1) 清理 driver 会话（best-effort）
        try:
            from driver.wx.service import clear_session

            clear_session()
        except Exception:
            pass

        # 2) 清理任务队列（best-effort）
        try:
            from core.jobs import TaskQueue

            TaskQueue.delete_queue()
        except Exception:
            pass

        logger.error("公众号平台登录失效,请重新登录")

    return WxGatherHooks(on_update_wechat_account=_on_update_wechat_account, on_error=_on_error)
