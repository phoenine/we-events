"""活动领域模块。"""

from core.integrations.supabase.client import supabase_client
from core.activities.repo import ActivitiesRepository
from core.activities.model import Activity


activity_repo = ActivitiesRepository(supabase_client)

__all__ = ["activity_repo", "Activity"]
