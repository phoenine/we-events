import type { ActivityExtractionSummary } from "@/types/api";


export function activityExtractionBatchButtonText(): string {
  return "一键抽取";
}

export function activityExtractionBatchConfirmation(
  pendingCount: number
): string {
  return `即将抽取 ${pendingCount} 篇文章，任务将在后台串行执行，是否继续？`;
}

export function shouldPollActivityExtraction(
  summary: ActivityExtractionSummary | null | undefined
): boolean {
  return Boolean(
    summary && summary.pending_count + summary.processing_count > 0
  );
}
