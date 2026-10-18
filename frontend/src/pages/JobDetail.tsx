import { Link, useParams } from "react-router-dom";
import { FreshnessBadge, SkillChips } from "../components/JobCard";
import { ErrorState, Loading } from "../components/States";
import { api } from "../lib/api";
import { deadline, freshness, jobTypeLabel, sourceLabel, whereLabel } from "../lib/format";
import { useAsync } from "../lib/useAsync";

/** Only http(s) links become buttons; anything else (javascript:, data:) is shown as plain text. */
export function safeUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
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
      <p><Link to="/">← All jobs</Link></p>
      <header className="card">
        <h1>{j.title}</h1>
        <p className="company">{j.company_name ?? "Unknown company"}</p>
        <p className="meta"><span>{whereLabel(j)}</span><span>{jobTypeLabel(j.job_type)}</span><span>via {sourceLabel(j.source)}</span></p>
        <p className="badges">
          <FreshnessBadge job={j} />
          {f.posted && <span className="badge">{f.posted}</span>}
          {due && <span className={`badge ${due.closed ? "closed" : "deadline"}`}>{due.text}</span>}
          {!j.is_active && <span className="badge closed">No longer listed by the source</span>}
          {match && <span className="badge score-badge">{Math.round(match.score)}% skills match</span>}
        </p>
        <div className="actions">
          {apply ? (
            <a className="btn primary" href={apply} target="_blank" rel="noopener noreferrer">
              Apply on the original posting ↗
            </a>
          ) : (
            <span className="muted">No valid apply link was provided.</span>
          )}
        </div>
      </header>

      <section className="card">
        <h2>Requirements</h2>
        <dl className="facts">
          <dt>Skills</dt><dd>{j.necessary_skills.length ? <SkillChips skills={j.necessary_skills} max={50} /> : "Not listed"}</dd>
          <dt>Minimum CGPA</dt><dd>{j.min_cgpa ?? "Not specified"}</dd>
          <dt>Branches</dt><dd>{j.allowed_branches.length ? j.allowed_branches.join(", ").toUpperCase() : "Any"}</dd>
          <dt>Graduation years</dt><dd>{j.allowed_grads.length ? j.allowed_grads.join(", ") : "Any"}</dd>
          <dt>Deadline</dt><dd>{j.deadline_at ?? "Not specified"}</dd>
        </dl>
      </section>

      <section className="card">
        <h2>Description</h2>
        {/* Rendered as text with line breaks kept: scraped content is never injected as HTML. */}
        <div className="description">{j.description?.trim() || "No description was provided by the source."}</div>
      </section>
    </article>
  );
}
