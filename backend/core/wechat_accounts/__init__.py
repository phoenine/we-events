"""公众号/订阅源领域模块。"""

from core.integrations.supabase.client import supabase_client
from core.wechat_accounts.repo import WeChatAccountRepository
from core.wechat_accounts.model import WeChatAccount


wechat_account_repo = WeChatAccountRepository(supabase_client)

__all__ = ["wechat_account_repo", "WeChatAccount"]
