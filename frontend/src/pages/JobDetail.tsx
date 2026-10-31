import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import { Cover, FreshnessBadge, SkillChips } from "../components/JobCard";
import { ErrorState, Loading } from "../components/States";
import { StatusSelect } from "../components/StatusSelect";
import { ApiError, api } from "../lib/api";
import { deadline, freshness, jobTypeLabel, safeUrl, sourceLabel, whereLabel } from "../lib/format";
import type { Application, ApplicationStatus } from "../lib/types";
import { useAsync } from "../lib/useAsync";

export { safeUrl };

/** Save the job to the tracker (always as "Saved"), or change its status once saved. Opening the apply link changes nothing here. */
function TrackJob({ jobId }: { jobId: number }) {
  // Like the match score, a nice-to-have: if the list fails to load, the Save button still works (duplicates get a 409).
  const list = useAsync(() => api.applications().catch(() => null), []);
  const [mine, setMine] = useState<Application>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const current = mine ?? list.data?.find((a) => a.job.id === jobId);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) list.reload(); // already saved (e.g. in another tab): show it
      else setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const save = () => run(async () => setMine(await api.saveJob(jobId)));
  const setStatus = (id: number, status: ApplicationStatus) => run(async () => setMine(await api.updateApplication(id, { status })));

  if (list.loading && !list.data) return null;
  return (
    <div className="track">
      {current ? (
        <>
          <div className="track-row">
            <span>Your status</span>
            <StatusSelect value={current.status} disabled={busy} label="Your application status" onChange={(s) => setStatus(current.id, s)} />
          </div>
          <Link to="/applications" className="track-link">View all applications</Link>
        </>
      ) : (
        <button type="button" className="btn block" disabled={busy} onClick={save}>
          <Icon name="bookmark" size={16} /> {busy ? "Saving…" : "Save job"}
        </button>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}

export function JobDetailPage() {
  const id = Number(useParams().id);
  const job = useAsync(() => api.job(id), [id]);
  // The match score is a nice-to-have: failing to load it must not hide the job.
  const matches = useAsync(() => api.matches({ include_unmatched: true }).catch(() => []), [id]);

  if (!Number.isInteger(id)) return <ErrorState error={new Error("That is not a valid job link.")} />;
  if (job.loading && !job.data) return <Loading label="Loading job…" />;
  if (job.error) return <ErrorState error={job.error.name === "ApiError" && /not found/i.test(job.error.message) ? new Error("This job doesn't exist (or was removed).") : job.error} onRetry={job.reload} />;
  const j = job.data!;
  const match = matches.data?.find((m) => m.job.id === j.id);
  const apply = safeUrl(j.apply_url);
  const due = deadline(j);
  const f = freshness(j);
  return (
    <article className="detail">
      <Link to="/jobs" className="back">
        <Icon name="left" size={16} /> All jobs
      </Link>
      <header className="detail-head">
        <h1>{j.title}</h1>
        <p className="detail-sub">
          <strong>{j.company_name ?? "Unknown company"}</strong>
          <span aria-hidden="true">·</span>
          <span>{whereLabel(j)}</span>
          <span aria-hidden="true">·</span>
          <span>{jobTypeLabel(j.job_type)}</span>
        </p>
      </header>

      <Cover company={j.company_name} className="banner" />

      <div className="detail-grid">
        <div className="detail-main">
          <section className="host">
            <Cover company={j.company_name} className="host-avatar" />
            <div>
              <h2>Hiring: {j.company_name ?? "Unknown company"}</h2>
              <p className="muted">Collected via {sourceLabel(j.source)}</p>
            </div>
          </section>

          <ul className="highlights">
            <li>
              <Icon name="refresh" size={22} />
              <div>
                <strong>Freshness</strong>
                <p className="badges">
                  <FreshnessBadge job={j} />
                  {f.posted && <span className="badge">{f.posted}</span>}
                  {!j.is_active && <span className="badge closed">No longer listed by the source</span>}
                </p>
              </div>
            </li>
            <li>
              <Icon name="pin" size={22} />
              <div>
                <strong>{whereLabel(j)}</strong>
                <p className="muted">{j.is_remote ? "Remote work is possible for this role." : "Check the posting for the office location."}</p>
              </div>
            </li>
          </ul>

          <section className="block">
            <h2>Requirements</h2>
            <dl className="facts">
              <dt>Skills</dt><dd>{j.necessary_skills.length ? <SkillChips skills={j.necessary_skills} max={50} /> : "Not listed"}</dd>
              <dt>Minimum CGPA</dt><dd>{j.min_cgpa ?? "Not specified"}</dd>
              <dt>Branches</dt><dd>{j.allowed_branches.length ? j.allowed_branches.join(", ").toUpperCase() : "Any"}</dd>
              <dt>Graduation years</dt><dd>{j.allowed_grads.length ? j.allowed_grads.join(", ") : "Any"}</dd>
              <dt>Deadline</dt><dd>{j.deadline_at ?? "Not specified"}</dd>
            </dl>
          </section>

          <section className="block">
            <h2>About the role</h2>
            {/* Rendered as text with line breaks kept: scraped content is never injected as HTML. */}
            <div className="description">{j.description?.trim() || "No description was provided by the source."}</div>
          </section>
        </div>

        <aside className="apply-box" aria-label="Apply">
          <div className="apply-top">
            <strong className="apply-type">{jobTypeLabel(j.job_type)}</strong>
            {match && match.score > 0 && <span className="badge score-badge">{Math.round(match.score)}% skills match</span>}
          </div>
          {due && <p className={`due ${due.closed ? "closed" : ""}`}><Icon name="calendar" size={16} /> {due.text}</p>}
          {apply ? (
            <a className="btn primary block" href={apply} target="_blank" rel="noopener noreferrer">
              Apply on the original posting <Icon name="external" size={16} />
            </a>
          ) : (
            <span className="muted">No valid apply link was provided.</span>
          )}
          <TrackJob key={j.id} jobId={j.id} />
          <p className="fine">You apply on {sourceLabel(j.source)}. Always confirm the details there.</p>
        </aside>
      </div>
    </article>
  );
}
