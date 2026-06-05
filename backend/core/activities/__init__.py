"""活动领域模块。"""

from core.integrations.supabase.client import supabase_client
from core.activities.repo import ActivitiesRepository, ActivityExtractionRunsRepository
from core.activities.model import Activity


activity_repo = ActivitiesRepository(supabase_client)
activity_run_repo = ActivityExtractionRunsRepository(supabase_client)

__all__ = ["activity_repo", "activity_run_repo", "Activity"]
