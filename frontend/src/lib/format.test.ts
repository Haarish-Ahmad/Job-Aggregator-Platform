import { NOW, job } from "../test/fixtures";
import { deadline, freshness, jobTypeLabel, parseList, relativeDays, sourceLabel, whereLabel } from "./format";

describe("freshness", () => {
  it("is fresh when the scraper saw the posting in the last 3 days", () => {
    const f = freshness({ last_seen_at: "2026-10-18T06:00:00", scraped_at: "2026-10-01T00:00:00", posted_date: null }, NOW);
    expect(f.level).toBe("fresh");
    expect(f.label).toBe("Last checked today");
    expect(f.isNew).toBe(false);
  });
  it("goes stale after 10 days without being seen", () => {
    expect(freshness({ last_seen_at: "2026-10-05T00:00:00", scraped_at: "2026-09-01T00:00:00", posted_date: null }, NOW).level).toBe("stale");
    expect(freshness({ last_seen_at: "2026-10-12T00:00:00", scraped_at: "2026-09-01T00:00:00", posted_date: null }, NOW).level).toBe("ok");
  });
  it("marks postings first stored within 3 days as new", () => {
    expect(freshness(job({ scraped_at: "2026-10-17T10:00:00" }), NOW).isNew).toBe(true);
    expect(freshness(job({ scraped_at: "2026-10-01T10:00:00" }), NOW).isNew).toBe(false);
  });
  it("copes with missing dates", () => {
    const f = freshness({ last_seen_at: null, scraped_at: null, posted_date: null }, NOW);
    expect(f).toMatchObject({ level: "stale", isNew: false, posted: null });
  });
  it("describes the source posting date when known", () => {
    expect(freshness(job({ posted_date: "2026-10-11" }), NOW).posted).toBe("Posted 7 days ago");
  });
});

describe("deadline", () => {
  it.each([
    ["2026-10-17", "Closed", true],
    ["2026-10-18", "Closes today", false],
    ["2026-10-19", "Closes tomorrow", false],
    ["2026-10-28", "Closes in 10 days", false],
  ])("%s -> %s", (d, text, closed) => expect(deadline({ deadline_at: d }, NOW)).toEqual({ text, closed }));
  it("is null without a deadline or with garbage", () => {
    expect(deadline({ deadline_at: null }, NOW)).toBeNull();
    expect(deadline({ deadline_at: "soon" }, NOW)).toBeNull();
  });
});

describe("labels", () => {
  it("relativeDays", () => {
    expect([relativeDays(0), relativeDays(1), relativeDays(12), relativeDays(45), relativeDays(null)]).toEqual(["today", "yesterday", "12 days ago", "1 month ago", "unknown"]);
  });
  it("jobTypeLabel", () => {
    expect(jobTypeLabel("full_time")).toBe("Full time");
    expect(jobTypeLabel(null)).toBe("Not specified");
  });
  it("whereLabel", () => {
    expect(whereLabel({ location: "Pune", is_remote: false })).toBe("Pune");
    expect(whereLabel({ location: null, is_remote: true })).toBe("Remote");
    expect(whereLabel({ location: "Work from home", is_remote: true })).toBe("Remote");
    expect(whereLabel({ location: "Pune", is_remote: true })).toBe("Pune · Remote OK");
    expect(whereLabel({ location: null, is_remote: false })).toBe("Location not specified");
  });
  it("sourceLabel", () => {
    expect(sourceLabel("shine")).toBe("Shine");
    expect(sourceLabel(null)).toBe("Added manually");
    expect(sourceLabel("other")).toBe("other");
  });
  it("parseList lowercases, trims and dedupes", () => {
    expect(parseList(" Python, SQL ,python,, ")).toEqual(["python", "sql"]);
  });
});
