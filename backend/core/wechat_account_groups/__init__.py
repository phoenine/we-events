"""公众号分组领域模块。"""

from core.integrations.supabase.client import supabase_client
from core.wechat_account_groups.repo import WeChatAccountGroupRepository
from core.wechat_account_groups.model import WeChatAccountGroup


wechat_account_group_repo = WeChatAccountGroupRepository(supabase_client)

__all__ = ["wechat_account_group_repo", "WeChatAccountGroup"]
