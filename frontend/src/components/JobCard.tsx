import { Link } from "react-router-dom";
import { deadline, freshness, jobTypeLabel, sourceLabel, whereLabel } from "../lib/format";
import type { Job } from "../lib/types";

export function FreshnessBadge({ job, now }: { job: Job; now?: Date }) {
  const f = freshness(job, now);
  return (
    <>
      {f.isNew && <span className="badge new">New</span>}
      <span className={`badge fresh-${f.level}`} title="When the scraper last saw this posting on the source site">
        {f.label}
      </span>
    </>
  );
}

export function SkillChips({ skills, max = 6 }: { skills: string[]; max?: number }) {
  if (skills.length === 0) return null;
  return (
    <ul className="chips" aria-label="Skills">
      {skills.slice(0, max).map((s) => (
        <li key={s}>{s}</li>
      ))}
      {skills.length > max && <li className="more">+{skills.length - max}</li>}
    </ul>
  );
}

export function JobCard({ job, score, now }: { job: Job; score?: number; now?: Date }) {
  const due = deadline(job, now);
  return (
    <article className="card job">
      <div className="job-head">
        <h3>
          <Link to={`/jobs/${job.id}`}>{job.title}</Link>
        </h3>
        {score !== undefined && (
          <span className="score" title="Share of the required skills you have" aria-label={`${Math.round(score)} percent match`}>
            {Math.round(score)}%
          </span>
        )}
      </div>
      <p className="company">{job.company_name ?? "Unknown company"}</p>
      <p className="meta">
        <span>{whereLabel(job)}</span>
        <span>{jobTypeLabel(job.job_type)}</span>
        <span>{sourceLabel(job.source)}</span>
      </p>
      <SkillChips skills={job.necessary_skills} />
      <p className="badges">
        <FreshnessBadge job={job} now={now} />
        {due && <span className={`badge ${due.closed ? "closed" : "deadline"}`}>{due.text}</span>}
      </p>
    </article>
  );
}
