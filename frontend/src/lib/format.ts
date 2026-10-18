import type { Job } from "./types";

const DAY = 86_400_000;

/** Whole days since `iso`. A date-only value ("2026-10-11") is a calendar date, compared in the viewer's calendar. */
function ageInDays(iso: string | null, now: Date): number | null {
  if (!iso) return null;
  const dateOnly = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) {
    const day = Date.UTC(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
    const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.max(0, Math.round((today - day) / DAY));
  }
  // Backend timestamps are naive UTC ("2026-10-18T06:00:00"): treat them as UTC.
  const t = Date.parse(/Z|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(t) ? null : Math.max(0, Math.floor((now.getTime() - t) / DAY));
}

export function relativeDays(days: number | null): string {
  if (days === null) return "unknown";
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

export type FreshnessLevel = "fresh" | "ok" | "stale";

export interface Freshness {
  level: FreshnessLevel;
  label: string;
  isNew: boolean;
  posted: string | null;
}

/**
 * How current a listing is. `last_seen_at` is when the scraper last saw it on the source site, so an old
 * value means the posting may have been taken down. `isNew` = first stored within the last 3 days.
 */
export function freshness(job: Pick<Job, "last_seen_at" | "scraped_at" | "posted_date">, now: Date = new Date()): Freshness {
  const seen = ageInDays(job.last_seen_at ?? job.scraped_at, now);
  const first = ageInDays(job.scraped_at, now);
  const posted = ageInDays(job.posted_date, now);
  const level: FreshnessLevel = seen === null || seen > 10 ? "stale" : seen > 3 ? "ok" : "fresh";
  return {
    level,
    label: seen === null ? "Last checked: unknown" : `Last checked ${relativeDays(seen)}`,
    isNew: first !== null && first <= 3,
    posted: posted === null ? null : `Posted ${relativeDays(posted)}`,
  };
}

export type Deadline = { text: string; closed: boolean } | null;

export function deadline(job: Pick<Job, "deadline_at">, now: Date = new Date()): Deadline {
  const m = job.deadline_at?.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  // A deadline is a calendar date, so compare whole days in the viewer's own calendar (not hours).
  const due = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.round((due - today) / DAY);
  if (days < 0) return { text: "Closed", closed: true };
  if (days === 0) return { text: "Closes today", closed: false };
  return { text: days === 1 ? "Closes tomorrow" : `Closes in ${days} days`, closed: false };
}

export function jobTypeLabel(type: string | null): string {
  if (!type) return "Not specified";
  return type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function whereLabel(job: Pick<Job, "location" | "is_remote">): string {
  if (job.is_remote && job.location && !/work from home|remote/i.test(job.location)) return `${job.location} · Remote OK`;
  if (job.is_remote) return "Remote";
  return job.location ?? "Location not specified";
}

export function sourceLabel(source: string | null): string {
  if (!source) return "Added manually";
  return { shine: "Shine", internshala: "Internshala", unstop: "Unstop", greenhouse: "Greenhouse", microsoft: "Microsoft Careers", google: "Google Careers", ycombinator: "Y Combinator" }[source] ?? source;
}

export function parseList(text: string): string[] {
  return [...new Set(text.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean))];
}
