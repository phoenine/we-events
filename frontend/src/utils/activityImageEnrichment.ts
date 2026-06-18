import type { Activity, ActivityImageEnrichmentPreview } from "@/types/api";

export const ENRICHABLE_ACTIVITY_FIELDS = [
  "event_time_text",
  "start_at",
  "end_at",
  "location_text",
  "registration_text",
  "registration_method",
  "registration_url",
  "fee_text",
  "audience",
] as const;

export type EnrichableActivityField = (typeof ENRICHABLE_ACTIVITY_FIELDS)[number];

export function isActivityEnrichmentPreviewCurrent(
  activity: Pick<Activity, "id"> | null | undefined,
  preview: Pick<ActivityImageEnrichmentPreview, "activity_id"> | null | undefined
): boolean {
  return Boolean(activity && preview && activity.id === preview.activity_id);
}

export function hasCriticalActivityGap(activity: Activity): boolean {
  const missingTime = !activity.event_time_text && !activity.start_at;
  const missingLocation = !activity.location_text?.trim();
  const method = activity.registration_method || "unknown";
  const hasRegistrationHint =
    !["none", "unknown"].includes(method) ||
    Boolean(activity.registration_text?.trim() || activity.registration_url?.trim());
  const missingRegistration =
    hasRegistrationHint &&
    (method === "unknown" ||
      !Boolean(activity.registration_text?.trim() || activity.registration_url?.trim()));
  return missingTime || missingLocation || missingRegistration;
}

export function defaultSelectedSuggestionFields(
  activity: Activity,
  preview: ActivityImageEnrichmentPreview
): EnrichableActivityField[] {
  return ENRICHABLE_ACTIVITY_FIELDS.filter((field) => {
    const suggestion = preview.suggestions[field];
    const current = activity[field];
    return suggestion !== undefined && suggestion !== null && suggestion !== "" && !current;
  });
}

export function buildConfirmedEnrichmentUpdate(
  activity: Activity,
  preview: ActivityImageEnrichmentPreview,
  selectedFields: EnrichableActivityField[]
): Partial<Activity> {
  const update: Partial<Activity> = {};
  for (const field of selectedFields) {
    const value = preview.suggestions[field];
    if (value !== undefined && value !== null) {
      (update as Record<string, unknown>)[field] = value;
    }
  }
  update.evidence = [...(activity.evidence || []), ...(preview.evidence || [])];
  update.warnings = [...(activity.warnings || []), ...(preview.warnings || [])];
  return update;
}
