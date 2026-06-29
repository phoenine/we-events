export function endedActivityCleanupConfirmation() {
  return "将删除数据库中全部已结束活动，且不可恢复，是否继续？";
}

export function endedActivityCleanupSuccess(deletedCount: number) {
  return `已删除 ${deletedCount} 个活动`;
}
