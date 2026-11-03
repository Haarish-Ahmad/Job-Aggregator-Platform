import { useState, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CompanyLogo } from "../components/JobCard";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { StatusSelect } from "../components/StatusSelect";
import { api } from "../lib/api";
import { shortDate } from "../lib/format";
import type { Application, ApplicationUpdate } from "../lib/types";
import { useAsync } from "../lib/useAsync";

type Tab = "all" | "saved" | "applied" | "selected" | "rejected";
const TABS: { id: Tab; label: string; matches: (a: Application) => boolean }[] = [
  { id: "all", label: "All", matches: () => true },
  { id: "saved", label: "Saved", matches: (a) => a.status === "saved" },
  { id: "applied", label: "Applied", matches: (a) => a.status === "applied" },
  // "Selected" is a filter, not a status: interviews and offers together.
  { id: "selected", label: "Selected", matches: (a) => a.status === "interview" || a.status === "offer" },
  { id: "rejected", label: "Rejected", matches: (a) => a.status === "rejected" },
];

export function ApplicationsPage() {
  const { data, error, loading, reload } = useAsync(() => api.applications(), []);
  // Edits and removals are kept here, over the loaded list, so counts and tabs follow every change without refetching.
  const [edited, setEdited] = useState<Record<number, Application>>({});
  const [removed, setRemoved] = useState<number[]>([]);
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t.id === params.get("tab")) ?? TABS[0];

  const all = data?.filter((a) => !removed.includes(a.id)).map((a) => edited[a.id] ?? a);
  const shown = all?.filter(tab.matches);
  const select = (id: Tab) => setParams(id === "all" ? {} : { tab: id }, { replace: true });

  return (
    <>
      <section className="page-head">
        <h1>Applications</h1>
        <p className="lead">Jobs you saved, and where each application stands. You apply on the original posting; change the status here as things move.</p>
      </section>
      {loading && !data && <Loading label="Loading your applications…" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {all && (
        <>
          <AppTabs current={tab.id} counts={Object.fromEntries(TABS.map((t) => [t.id, all.filter(t.matches).length])) as Record<Tab, number>} onSelect={select} />
          <div role="tabpanel" id="app-panel" aria-labelledby={`app-tab-${tab.id}`}>
            {shown!.length === 0 ? (
              <EmptyFor tab={tab.id} />
            ) : (
              <ul className="app-list">
                {shown!.map((a) => (
                  <ApplicationRow
                    key={a.id}
                    app={a}
                    onUpdated={(next) => setEdited((e) => ({ ...e, [next.id]: next }))}
                    onRemoved={() => setRemoved((r) => [...r, a.id])}
                  />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </>
  );
}

function AppTabs({ current, counts, onSelect }: { current: Tab; counts: Record<Tab, number>; onSelect: (tab: Tab) => void }) {
  // Arrow keys move between tabs (the usual tablist behaviour); Tab moves on to the list.
  function onKeyDown(e: KeyboardEvent) {
    const i = TABS.findIndex((t) => t.id === current);
    const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const id = TABS[(next + TABS.length) % TABS.length].id;
    onSelect(id);
    document.getElementById(`app-tab-${id}`)?.focus();
  }
  return (
    <div className="app-tabs" role="tablist" aria-label="Filter applications" onKeyDown={onKeyDown}>
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          id={`app-tab-${t.id}`}
          aria-selected={t.id === current}
          aria-controls="app-panel"
          tabIndex={t.id === current ? 0 : -1}
          className={`tab-${t.id}${t.id === current ? " active" : ""}`}
          onClick={() => onSelect(t.id)}
        >
          {t.label}
          <span className="app-count">{counts[t.id]}</span>
        </button>
      ))}
    </div>
  );
}

function EmptyFor({ tab }: { tab: Tab }) {
  if (tab === "saved") return <EmptyState title="No saved jobs">Open a job and choose <strong>Save job</strong>.</EmptyState>;
  if (tab === "applied") return <EmptyState title="Nothing marked as applied yet">Change a job's status to <strong>Applied</strong> once you've applied on the company's site.</EmptyState>;
  if (tab === "selected") return <EmptyState title="No interviews or offers yet">Jobs marked <strong>Interview</strong> or <strong>Offer received</strong> show up here.</EmptyState>;
  if (tab === "rejected") return <EmptyState title="No rejections">Jobs marked <strong>Rejected</strong> show up here.</EmptyState>;
  return (
    <EmptyState title="No saved jobs yet">
      Open a job and choose <strong>Save job</strong>. <Link to="/jobs">Browse jobs</Link>
    </EmptyState>
  );
}

function ApplicationRow({ app, onUpdated, onRemoved }: { app: Application; onUpdated: (app: Application) => void; onRemoved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const { job } = app;
  const company = job.company_name ?? "Unknown company";

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const update = (change: ApplicationUpdate) => run(async () => onUpdated(await api.updateApplication(app.id, change)));
  const remove = () => {
    if (!window.confirm(`Remove "${job.title}" at ${company} from your applications?`)) return;
    void run(async () => {
      await api.removeApplication(app.id);
      onRemoved();
    });
  };

  return (
    <li className="app-row">
      <CompanyLogo company={job.company_name} />
      <div className="app-main">
        <Link to={`/jobs/${job.id}`} className="app-title">{job.title}</Link>
        <span className="app-sub">
          <span>{company}</span>
          {app.applied_on ? (
            <label className="app-date">
              Applied
              <input type="date" value={app.applied_on} disabled={busy} onChange={(e) => e.target.value && update({ applied_on: e.target.value })} />
            </label>
          ) : (
            <span>Saved {shortDate(app.saved_on)}</span>
          )}
          {!job.is_active && <span className="badge closed">No longer listed</span>}
        </span>
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
      <div className="app-actions">
        <StatusSelect value={app.status} disabled={busy} label={`Status for ${job.title} at ${company}`} onChange={(status) => update({ status })} />
        <button type="button" className="btn small ghost" disabled={busy} onClick={remove} aria-label={`Remove ${job.title} at ${company}`}>
          Remove
        </button>
      </div>
    </li>
  );
}
