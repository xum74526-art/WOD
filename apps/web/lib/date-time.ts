export const PLATFORM_TIME_ZONE = "Asia/Shanghai";

const LOCAL_DATE_TIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/;
const API_DATE_TIME_WITHOUT_OFFSET_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?$/;
const platformDateTimeFormatter = new Intl.DateTimeFormat("zh-CN-u-ca-gregory", {
  timeZone: PLATFORM_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Convert an instant to the wall-clock value expected by datetime-local. */
export function toLocalDateTimeInputValue(value: Date = new Date()) {
  if (Number.isNaN(value.getTime())) throw new RangeError("无效的日期时间");
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

/** Interpret a datetime-local wall-clock value in the browser's local time zone. */
export function localDateTimeInputToUtcIso(value: string) {
  const match = LOCAL_DATE_TIME_PATTERN.exec(value);
  if (!match) throw new RangeError("无效的本地日期时间");

  const [, yearPart, monthPart, dayPart, hourPart, minutePart, secondPart = "0", fractionPart = ""] = match;
  const year = Number(yearPart);
  const month = Number(monthPart) - 1;
  const day = Number(dayPart);
  const hour = Number(hourPart);
  const minute = Number(minutePart);
  const second = Number(secondPart);
  const millisecond = Number(fractionPart.padEnd(3, "0") || "0");
  const date = new Date(year, month, day, hour, minute, second, millisecond);

  if (
    date.getFullYear() !== year
    || date.getMonth() !== month
    || date.getDate() !== day
    || date.getHours() !== hour
    || date.getMinutes() !== minute
    || date.getSeconds() !== second
    || date.getMilliseconds() !== millisecond
  ) {
    throw new RangeError("无效的本地日期时间");
  }

  return date.toISOString();
}

/** API timestamps without an offset are UTC by backend contract, not browser-local time. */
export function parseApiUtcDateTime(value?: string | null) {
  if (!value?.trim()) return null;
  const normalized = value.trim().replace(" ", "T");
  const date = new Date(API_DATE_TIME_WITHOUT_OFFSET_PATTERN.test(normalized) ? `${normalized}Z` : normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatPlatformDateTime(value?: string | null) {
  const date = parseApiUtcDateTime(value);
  if (!date) return "—";
  const parts = Object.fromEntries(platformDateTimeFormatter.formatToParts(date).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}
