import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { JobCard } from "../components/JobCard";
import { Pagination } from "../components/Pagination";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { JobQuery, Scope, Sort } from "../lib/types";

export const PAGE_SIZE = 20;
const SCOPES: { value: Scope; label: string }[] = [
  { value: "india_remote", label: "India + remote" },
  { value: "india", label: "India only" },
  { value: "remote", label: "Remote only" },
  { value: "all", label: "Anywhere" },
];
const SORTS: { value: Sort; label: string }[] = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "deadline", label: "Closing soonest" },
  { value: "title", label: "Title A–Z" },
];
const TYPES = [
  { value: "", label: "Any type" },
  { value: "internship", label: "Internship" },
  { value: "full_time", label: "Full time" },
  { value: "part_time", label: "Part time" },
  { value: "contract", label: "Contract" },
];
const SOURCES = ["", "shine", "internshala", "unstop", "greenhouse", "microsoft", "google", "ycombinator"];

function narrowScreen(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(max-width: 640px)").matches;
}

export function queryFromParams(p: URLSearchParams): JobQuery & { page: number } {
  const page = Math.max(1, Number(p.get("page")) || 1);
  const grad = Number(p.get("grad_year"));
  return {
    q: p.get("q") ?? undefined,
    job_type: p.get("job_type") ?? undefined,
    location: p.get("location") ?? undefined,
    skill: p.get("skill") ?? undefined,
    grad_year: grad > 0 ? grad : undefined,
    source: p.get("source") ?? undefined,
    scope: (p.get("scope") as Scope) || "india_remote",
    sort: (p.get("sort") as Sort) || "newest",
    hide_expired: p.get("hide_expired") === "1",
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    page,
  };
}

export function ListingsPage() {
  const [params, setParams] = useSearchParams();
  const { page, ...query } = queryFromParams(params);
  const { data, error, loading, reload } = useAsync(() => api.jobs(query), [params.toString()]);

  // Text fields apply on submit; selects and the checkbox apply immediately.
  const [text, setText] = useState({ q: query.q ?? "", location: query.location ?? "", skill: query.skill ?? "", grad_year: query.grad_year ? String(query.grad_year) : "" });
  useEffect(() => {
    setText({ q: query.q ?? "", location: query.location ?? "", skill: query.skill ?? "", grad_year: query.grad_year ? String(query.grad_year) : "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.toString()]);

  function update(changes: Record<string, string | undefined>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === undefined || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  }
  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    update({ q: text.q.trim(), location: text.location.trim(), skill: text.skill.trim(), grad_year: text.grad_year });
  };
  const filtered = ["q", "job_type", "location", "skill", "grad_year", "source", "hide_expired"].some((k) => params.get(k));

  return (
    <>
      <h1>Jobs & internships</h1>
      {/* On a phone the filters start collapsed so the results are visible; on wider screens they are always open. */}
      <details className="filter-panel" open={!narrowScreen()}>
        <summary className="btn">Filters{filtered ? " (active)" : ""}</summary>
      <form className="filters card" onSubmit={onSearch} role="search" aria-label="Filter jobs">
        <label className="grow">
          Search
          <input type="search" value={text.q} onChange={(e) => setText({ ...text, q: e.target.value })} placeholder="Title or company" />
        </label>
        <label>
          Where
          <select value={query.scope} onChange={(e) => update({ scope: e.target.value })}>
            {SCOPES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
        <label>
          Type
          <select value={query.job_type ?? ""} onChange={(e) => update({ job_type: e.target.value })}>
            {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        <label>
          City
          <input value={text.location} onChange={(e) => setText({ ...text, location: e.target.value })} placeholder="e.g. Pune" />
        </label>
        <label>
          Skill
          <input value={text.skill} onChange={(e) => setText({ ...text, skill: e.target.value })} placeholder="e.g. python" />
        </label>
        <label>
          Graduating
          <input type="number" min="2000" max="2100" value={text.grad_year} onChange={(e) => setText({ ...text, grad_year: e.target.value })} placeholder="2026" />
        </label>
        <label>
          Source
          <select value={query.source ?? ""} onChange={(e) => update({ source: e.target.value })}>
            {SOURCES.map((s) => <option key={s} value={s}>{s || "Any source"}</option>)}
          </select>
        </label>
        <label>
          Sort
          <select value={query.sort} onChange={(e) => update({ sort: e.target.value })}>
            {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={!!query.hide_expired} onChange={(e) => update({ hide_expired: e.target.checked ? "1" : undefined })} />
          Hide closed
        </label>
        <button className="btn primary">Search</button>
        {filtered && (
          <button type="button" className="btn" onClick={() => setParams(new URLSearchParams({ scope: query.scope ?? "india_remote" }))}>
            Clear filters
          </button>
        )}
      </form>
      </details>

      {loading && !data && <Loading label="Loading jobs…" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <section aria-busy={loading} aria-label="Results">
          <p className="count" aria-live="polite">
            {data.total === 0 ? "No jobs" : `${data.total} job${data.total === 1 ? "" : "s"}`}
          </p>
          {data.jobs.length === 0 ? (
            <EmptyState title="No jobs match these filters">
              Try a different search, widen “Where” to <button className="link" onClick={() => update({ scope: "all" })}>Anywhere</button>, or clear the filters.
            </EmptyState>
          ) : (
            <div className="grid">{data.jobs.map((job) => <JobCard key={job.id} job={job} />)}</div>
          )}
          <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={(p) => update({ page: String(p) })} />
        </section>
      )}
    </>
  );
}
