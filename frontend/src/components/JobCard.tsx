import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import { companyHue, deadline, freshness, initials, jobTypeLabel, sourceLabel, whereLabel } from "../lib/format";
import type { Job } from "../lib/types";
import { Icon } from "./Icon";

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

/** Scraped postings have no photos, so each company gets a coloured cover with its initials instead. */
export function Cover({ company, className = "", children }: { company: string | null; className?: string; children?: ReactNode }) {
  return (
    <div className={`cover ${className}`} style={{ "--h": companyHue(company) } as CSSProperties}>
      <span className="monogram" aria-hidden="true">
        {initials(company)}
      </span>
      {children}
    </div>
  );
}

export function JobCard({ job, score, now }: { job: Job; score?: number; now?: Date }) {
  const due = deadline(job, now);
  const f = freshness(job, now);
  return (
    <article className="job-card">
      <Cover company={job.company_name}>
        <div className="cover-top">
          {f.isNew ? (
            <span className="pill">
              <Icon name="sparkle" size={13} /> New
            </span>
          ) : (
            <span />
          )}
          {score !== undefined && (
            <span className="score" title="Share of the required skills you have" aria-label={`${Math.round(score)} percent match`}>
              {Math.round(score)}%
            </span>
          )}
        </div>
        <span className="pill cover-type">{jobTypeLabel(job.job_type)}</span>
      </Cover>
      <div className="job-body">
        <h3>
          {/* The link covers the whole card (see .stretched), so the card is one big click target. */}
          <Link className="stretched" to={`/jobs/${job.id}`}>
            {job.title}
          </Link>
        </h3>
        <p className="company">{job.company_name ?? "Unknown company"}</p>
        <p className="meta">
          <Icon name="pin" size={14} />
          <span>{whereLabel(job)}</span>
        </p>
        <SkillChips skills={job.necessary_skills} max={4} />
        <p className="card-foot">
          <span className={`dot fresh-${f.level}`} aria-hidden="true" />
          <span title="When the scraper last saw this posting on the source site">{f.label}</span>
          <span className="sep" aria-hidden="true">·</span>
          <span>{sourceLabel(job.source)}</span>
        </p>
        {due && <p className={`due ${due.closed ? "closed" : ""}`}>{due.text}</p>}
      </div>
    </article>
  );
}
