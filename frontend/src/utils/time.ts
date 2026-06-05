import dayjs from "dayjs";

export function formatEpochSeconds(value?: string | number | null) {
  if (value === undefined || value === null || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "-";
  const millis = numeric > 10_000_000_000 ? numeric : numeric * 1000;
  return dayjs(millis).format("YYYY-MM-DD HH:mm");
}
