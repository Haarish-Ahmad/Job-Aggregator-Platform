import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import { companyHue, deadline, freshness, initials, jobTypeLabel, safeUrl, sourceLabel, whereLabel, workModeLabel } from "../lib/format";
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

/** A square tile with the company's first letter, tinted with the company's own colour. */
export function CompanyLogo({ company }: { company: string | null }) {
  return (
    <span className="logo" style={{ "--h": companyHue(company) } as CSSProperties} aria-hidden="true">
      {initials(company).slice(0, 1)}
    </span>
  );
}

const MAX_SKILL_TAGS = 3;

export function JobCard({ job, score, now }: { job: Job; score?: number; now?: Date }) {
  const due = deadline(job, now);
  const f = freshness(job, now);
  const apply = safeUrl(job.apply_url);
  const mode = workModeLabel(job);
  const company = job.company_name ?? "Unknown company";
  const skills = job.necessary_skills;
  return (
    <article className="job-card">
      <header className="job-top">
        <CompanyLogo company={job.company_name} />
        <div className="org">
          <strong>{company}</strong>
          <span className="org-sub">{whereLabel(job)}</span>
        </div>
        {/* When the source gives a posting date, show it; otherwise when the scraper last saw the posting. */}
        <span className={`posted fresh-${f.level}`} title="When the scraper last saw this posting on the source site">
          {f.posted ?? f.label}
        </span>
      </header>

      <h3>
        {/* The link covers the whole card (see .stretched), so the card is one big click target. */}
        <Link className="stretched" to={`/jobs/${job.id}`}>
          {job.title}
        </Link>
      </h3>

      <ul className="tags" aria-label="Tags">
        {mode && <li>{mode}</li>}
        <li>{jobTypeLabel(job.job_type)}</li>
        {skills.slice(0, MAX_SKILL_TAGS).map((s) => (
          <li key={s}>{s}</li>
        ))}
        {skills.length > MAX_SKILL_TAGS && <li className="more">+{skills.length - MAX_SKILL_TAGS}</li>}
      </ul>

      <footer className="job-bottom">
        <div className="job-status">
          {score !== undefined && (
            <span className="score" title="Share of the required skills you have" aria-label={`${Math.round(score)} percent match`}>
              {Math.round(score)}% match
            </span>
          )}
          {/* "New" next to an old posting date reads as a contradiction: this is new to our site. */}
          {f.isNew && <span className="badge new" title="Added to this site in the last 3 days">Just added</span>}
          {due ? <span className={`due ${due.closed ? "closed" : ""}`}>{due.text}</span> : <span className="via">via {sourceLabel(job.source)}</span>}
        </div>
        {apply ? (
          <a className="apply-btn" href={apply} target="_blank" rel="noopener noreferrer" aria-label={`Apply for ${job.title} at ${company} (opens the original posting)`}>
            Apply
          </a>
        ) : (
          <Link className="apply-btn quiet" to={`/jobs/${job.id}`} aria-label={`Details for ${job.title}`}>
            Details
          </Link>
        )}
      </footer>
    </article>
  );
}
