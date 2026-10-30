import "@fontsource-variable/inter";
import "@fontsource/instrument-serif/latin-400-italic.css";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { Icon, type IconName } from "../components/Icon";
import { Brand } from "../components/Layout";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { initials } from "../lib/format";
import type { Job } from "../lib/types";
import { useAsync } from "../lib/useAsync";

interface PreviewRow {
  key: string | number;
  title: string;
  company: string;
  skills: string[];
  score?: number;
  to?: string;
}

// Shown to signed-out visitors: the backend only serves jobs to signed-in users, so these are labelled as an example.
const EXAMPLES: PreviewRow[] = [
  { key: "g", title: "Software Engineering Intern", company: "Google", skills: ["Python", "Distributed Systems", "Cloud"], score: 95, to: "/register" },
  { key: "m", title: "Applied Scientist Intern", company: "Microsoft", skills: ["Machine Learning", "Python", "LLMs"], score: 92, to: "/register" },
  { key: "a", title: "SDE Intern", company: "Amazon", skills: ["Java", "System Design", "AWS"], score: 88, to: "/register" },
];

// Marks for a few well-known employers; everyone else gets their initial on a tile.
const COMPANY_MARKS: Record<string, ReactNode> = {
  google: (
    <svg viewBox="0 0 48 48" width="32" height="32">
      <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 8 3l5.7-5.7C34 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.7-.4-3.9z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 8 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2A11.9 11.9 0 0 1 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3a12 12 0 0 1-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.7-.4-3.9z" />
    </svg>
  ),
  microsoft: (
    <svg viewBox="0 0 21 21" width="28" height="28">
      <rect x="0" y="0" width="10" height="10" fill="#F25022" />
      <rect x="11" y="0" width="10" height="10" fill="#7FBA00" />
      <rect x="0" y="11" width="10" height="10" fill="#00A4EF" />
      <rect x="11" y="11" width="10" height="10" fill="#FFB900" />
    </svg>
  ),
  amazon: (
    <svg viewBox="0 0 24 24" width="34" height="34">
      <text x="12" y="15.5" textAnchor="middle" fontSize="20" fontWeight="700" fontFamily="Arial, sans-serif" fill="#14141a">a</text>
      <path d="M3.5 18c4.6 2.8 11.4 2.8 16-.3" fill="none" stroke="#FF9900" strokeWidth="1.9" strokeLinecap="round" />
      <path d="M17.2 16.6l2.7.8-.6 2.6" fill="none" stroke="#FF9900" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

function CompanyMark({ company }: { company: string }) {
  const mark = COMPANY_MARKS[company.trim().toLowerCase()];
  return mark ? (
    <span className="home-logo is-mark" aria-hidden="true">{mark}</span>
  ) : (
    <span className="home-logo" aria-hidden="true">{initials(company).slice(0, 1)}</span>
  );
}

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: "search", title: "Job discovery", text: "The latest off-campus openings, collected from job boards and career pages in one feed." },
  { icon: "file", title: "Resume-based matching", text: "We read the skills in each posting and in your resume, then rank the best fits first." },
  { icon: "bell", title: "Personalized alerts", text: "Get notified when new roles match your skills and preferences." },
];

function toRow(job: Job, score?: number): PreviewRow {
  return { key: job.id, title: job.title, company: job.company_name ?? "Unknown company", skills: job.necessary_skills.slice(0, 3), score, to: `/jobs/${job.id}` };
}

/** The signed-in user's best matches; their newest jobs instead when nothing matches yet (e.g. no skills on the profile). */
async function loadPreview(): Promise<{ rows: PreviewRow[]; matched: boolean }> {
  const matches = await api.matches();
  if (matches.length) {
    const best = [...matches].sort((a, b) => b.score - a.score).slice(0, 3);
    return { rows: best.map(({ job, score }) => toRow(job, Math.round(score))), matched: true };
  }
  const { jobs } = await api.jobs({ limit: 3, scope: "india_remote" });
  return { rows: jobs.map((j) => toRow(j)), matched: false };
}

function PreviewCard({ title, badge, seeAll, children }: { title: string; badge?: string; seeAll: { to: string; label: string }; children: ReactNode }) {
  return (
    <section className="home-preview" aria-label={title}>
      <div className="home-preview-head">
        <span>
          {title}
          {badge && <span className="home-badge">{badge}</span>}
        </span>
        <Link to={seeAll.to}>
          {seeAll.label} <Icon name="arrow" size={14} />
        </Link>
      </div>
      {children}
    </section>
  );
}

function Rows({ rows }: { rows: PreviewRow[] }) {
  return (
    <ul className="home-rows">
      {rows.map((r) => {
        const body = (
          <>
            <CompanyMark company={r.company} />
            <span className="home-row-main">
              <span className="home-row-text">
                <span className="home-row-title">{r.title}</span>
                <span className="home-row-co">{r.company}</span>
              </span>
              {r.skills.length > 0 && (
                <span className="home-chips">
                  {r.skills.map((s) => <span key={s}>{s}</span>)}
                </span>
              )}
            </span>
            {r.score !== undefined && <span className="home-match">{r.score}% match</span>}
            {r.to && <Icon name="right" size={16} className="home-chevron" />}
          </>
        );
        return <li key={r.key}>{r.to ? <Link to={r.to} className="home-row">{body}</Link> : <div className="home-row">{body}</div>}</li>;
      })}
    </ul>
  );
}

function MatchesPreview() {
  const { data, error, loading } = useAsync(loadPreview, []);
  const matched = data?.matched ?? true;
  return (
    <PreviewCard title={matched ? "Recommended for you" : "Latest openings"} seeAll={matched ? { to: "/matches", label: "See all" } : { to: "/jobs", label: "See all" }}>
      {loading && !data ? (
        <p className="home-preview-note">Loading your matches…</p>
      ) : error ? (
        <p className="home-preview-note">Couldn't load your matches right now.</p>
      ) : data && data.rows.length > 0 ? (
        <>
          <Rows rows={data.rows} />
          {!data.matched && (
            <p className="home-preview-note">
              Add skills to your <Link to="/profile">profile</Link> to see how well jobs match you.
            </p>
          )}
        </>
      ) : (
        <p className="home-preview-note">No openings yet. New jobs are collected every few hours.</p>
      )}
    </PreviewCard>
  );
}

export function HomePage() {
  const { user, checking, logout } = useAuth();
  return (
    <div className="home">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <div className="home-inner">
        <header className="home-head">
          <Link to="/" className="brand-link" aria-label="Job Aggregator home">
            <Brand />
          </Link>
          <nav aria-label="Main" className="home-nav">
            <NavLink to="/" end>Home</NavLink>
            <NavLink to="/jobs">Jobs</NavLink>
            <NavLink to="/matches">My matches</NavLink>
            <NavLink to="/analytics">Analytics</NavLink>
          </nav>
          <div className="home-actions">
            {checking ? null : user ? (
              <>
                <Link to="/profile" className="home-text-link">{user.name}</Link>
                <button type="button" className="home-text-link" onClick={() => logout()}>Sign out</button>
              </>
            ) : (
              <>
                <Link to="/login" className="home-text-link">Log in</Link>
                <Link to="/register" className="home-btn primary small">Sign up</Link>
              </>
            )}
          </div>
        </header>

        <main id="main" className="home-hero">
          <div className="home-copy">
            <p className="home-eyebrow">
              <span aria-hidden="true" />
              Off-campus opportunities, all in one place
            </p>
            <h1>
              Find jobs and internships that <em>match your skills.</em>
            </h1>
            <p className="home-lead">We gather openings from job boards and company career pages, read the skills they ask for, and match them to your resume.</p>
            <div className="home-ctas">
              <Link to={user ? "/matches" : "/register"} className="home-btn primary">
                Get started <Icon name="arrow" size={16} />
              </Link>
              <Link to="/jobs" className="home-btn ghost">Browse jobs</Link>
            </div>
          </div>
          {user ? (
            <MatchesPreview />
          ) : (
            <PreviewCard title="Recommended for you" badge="Example" seeAll={{ to: "/register", label: "See all" }}>
              <Rows rows={EXAMPLES} />
            </PreviewCard>
          )}
        </main>

        <section className="home-features" aria-label="Features">
          {FEATURES.map((f) => (
            <div key={f.title} className="home-feature">
              <Icon name={f.icon} size={22} />
              <h2>{f.title}</h2>
              <p>{f.text}</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
