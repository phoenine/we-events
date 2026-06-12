export interface CalendarEventInput {
  title: string;
  startsAt: string;
  endsAt?: string;
  location?: string;
  description?: string;
  url?: string;
  alarmMinutes?: number;
}

function escapeText(value: string) {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n")
    .replace(/,/g, "\\,")
    .replace(/;/g, "\\;");
}

function foldLine(line: string) {
  const chunks: string[] = [];
  let rest = line;
  while (rest.length > 75) {
    chunks.push(rest.slice(0, 75));
    rest = rest.slice(75);
  }
  chunks.push(rest);
  return chunks.map((chunk, index) => (index === 0 ? chunk : ` ${chunk}`)).join("\r\n");
}

function formatIcsDate(value: string | Date) {
  const date = value instanceof Date ? value : new Date(value);
  return date
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}Z$/, "Z");
}

function safeFilename(value: string) {
  return (value || "activity")
    .replace(/[\\/:*?"<>|]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
}

export function buildIcsEvent(input: CalendarEventInput) {
  const now = formatIcsDate(new Date());
  const uid = `${Date.now()}-${Math.random().toString(36).slice(2)}@we-events`;
  const endsAt =
    input.endsAt ||
    new Date(new Date(input.startsAt).getTime() + 2 * 60 * 60 * 1000).toISOString();

  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//we-events//activity-calendar//CN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    `UID:${uid}`,
    `DTSTAMP:${now}`,
    `DTSTART:${formatIcsDate(input.startsAt)}`,
    `DTEND:${formatIcsDate(endsAt)}`,
    `SUMMARY:${escapeText(input.title)}`,
  ];

  if (input.location) {
    lines.push(`LOCATION:${escapeText(input.location)}`);
  }
  if (input.description) {
    lines.push(`DESCRIPTION:${escapeText(input.description)}`);
  }
  if (input.url) {
    lines.push(`URL:${input.url}`);
  }
  if (input.alarmMinutes && input.alarmMinutes > 0) {
    lines.push("BEGIN:VALARM");
    lines.push(`TRIGGER:-PT${input.alarmMinutes}M`);
    lines.push("ACTION:DISPLAY");
    lines.push(`DESCRIPTION:${escapeText(input.title)}`);
    lines.push("END:VALARM");
  }

  lines.push("END:VEVENT", "END:VCALENDAR");
  return `${lines.map(foldLine).join("\r\n")}\r\n`;
}

export function downloadIcs(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${safeFilename(filename)}.ics`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
