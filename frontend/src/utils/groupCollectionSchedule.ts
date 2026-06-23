import type {
  ArticleCollectionRunSummary,
  WechatAccountGroup,
} from "@/types/api";


export function formatGroupCollectionSchedule(
  group: Pick<
    WechatAccountGroup,
    "schedule_enabled" | "schedule_time" | "collection_pages"
  >
): string {
  if (!group.schedule_enabled || !group.schedule_time) return "未启用";
  return `每天 ${group.schedule_time.slice(0, 5)} · ${group.collection_pages || 1} 页`;
}

export function groupCollectionRunLabel(
  run: Pick<ArticleCollectionRunSummary, "status"> | null | undefined,
  scheduleError = ""
): string {
  if (scheduleError) return "触发失败";
  const labels: Record<ArticleCollectionRunSummary["status"], string> = {
    queued: "排队中",
    processing: "采集中",
    success: "成功",
    partial_success: "部分成功",
    failed: "失败",
    canceled: "已取消",
  };
  return run ? labels[run.status] : "尚未执行";
}

export function groupCollectionRunColor(
  run: Pick<ArticleCollectionRunSummary, "status"> | null | undefined,
  scheduleError = ""
): string {
  if (scheduleError) return "error";
  if (!run) return "default";
  if (["queued", "processing"].includes(run.status)) return "processing";
  if (run.status === "success") return "success";
  if (run.status === "partial_success") return "warning";
  return "error";
}

export function hasGroupCollectionResult(
  group: Pick<
    WechatAccountGroup,
    "last_scheduled_at" | "last_collection_run" | "last_schedule_error"
  >
): boolean {
  return Boolean(
    group.last_scheduled_at ||
      group.last_collection_run ||
      group.last_schedule_error
  );
}
