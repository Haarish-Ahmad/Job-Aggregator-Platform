import { NavLink, Navigate, Outlet, Route, Routes, useSearchParams } from "react-router-dom";
import { BarList, TrendChart } from "../components/charts";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { sourceLabel } from "../lib/format";
import type { Scope } from "../lib/types";
import { useAsync } from "../lib/useAsync";

function useScope(): [Scope, (s: Scope) => void] {
  const [p, setP] = useSearchParams();
  return [(p.get("scope") as Scope) || "india_remote", (s) => setP({ scope: s })];
}

function Shell() {
  const { user } = useAuth();
  const [scope, setScope] = useScope();
  const admin = user?.role === "admin";
  const q = `?scope=${scope}`;
  return (
    <>
      <h1>Analytics</h1>
      <div className="subnav">
        <nav aria-label="Analytics">
          <NavLink to={`skills${q}`}>Skills in demand</NavLink>
          <NavLink to={`companies${q}`}>Companies & hiring</NavLink>
          {admin && <NavLink to={`skill-gap${q}`}>Skill gap</NavLink>}
          {admin && <NavLink to={`curriculum${q}`}>Curriculum alignment</NavLink>}
        </nav>
        <label>
          Where
          <select value={scope} onChange={(e) => setScope(e.target.value as Scope)}>
            <option value="india_remote">India + remote</option>
            <option value="india">India only</option>
            <option value="remote">Remote only</option>
            <option value="all">Anywhere</option>
          </select>
        </label>
      </div>
      <Outlet />
    </>
  );
}

function SkillsView() {
  const [scope] = useScope();
  const { data, error, loading, reload } = useAsync(() => api.skills({ scope, limit: 20 }), [scope]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data || data.top.length === 0) return <EmptyState title="No skills data yet">Skills appear once jobs with listed skills have been collected.</EmptyState>;
  return (
    <>
      <section className="card">
        <h2>Most requested skills</h2>
        <p className="muted">Number of active postings that ask for each skill.</p>
        <BarList rows={data.top.map((s) => ({ label: s.skill, value: s.jobs }))} />
      </section>
      {data.trend.length > 0 && (
        <section className="card">
          <h2>Weekly trend: top 5 skills</h2>
          <TrendChart points={data.trend} />
        </section>
      )}
    </>
  );
}

function CompaniesView() {
  const [scope] = useScope();
  const { data, error, loading, reload } = useAsync(() => api.companies({ scope, limit: 15 }), [scope]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data || data.totals.active_jobs === 0) return <EmptyState title="No hiring data yet">Nothing matches this view. Try “Anywhere”.</EmptyState>;
  const t = data.totals;
  return (
    <>
      <div className="tiles">
        <div className="tile"><strong>{t.active_jobs}</strong><span>active postings</span></div>
        <div className="tile"><strong>{t.companies}</strong><span>companies</span></div>
        <div className="tile"><strong>{t.india}</strong><span>in India</span></div>
        <div className="tile"><strong>{t.remote}</strong><span>remote</span></div>
      </div>
      <section className="card">
        <h2>Who is hiring</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Company</th><th className="num">Postings</th><th className="num">Internships</th></tr></thead>
            <tbody>{data.top_companies.map((c) => <tr key={c.company}><td>{c.company}</td><td className="num">{c.jobs}</td><td className="num">{c.internships}</td></tr>)}</tbody>
          </table>
        </div>
      </section>
      <div className="two">
        <section className="card"><h2>By type</h2><BarList rows={data.by_type.map((x) => ({ label: x.type.replace("_", " "), value: x.jobs }))} /></section>
        <section className="card"><h2>By source</h2><BarList rows={data.by_source.map((x) => ({ label: sourceLabel(x.source), value: x.jobs }))} /></section>
      </div>
      {data.weekly.length > 0 && (
        <section className="card"><h2>Postings per week</h2><BarList rows={data.weekly.map((w) => ({ label: w.week, value: w.jobs }))} /></section>
      )}
    </>
  );
}

function SkillGapView() {
  const [scope] = useScope();
  const { data, error, loading, reload } = useAsync(() => api.skillGap({ scope, limit: 25 }), [scope]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data || data.skills.length === 0) return <EmptyState title="No skill-gap data yet">Needs job postings with skills and registered students.</EmptyState>;
  return (
    <section className="card">
      <h2>Skill gap</h2>
      <p className="muted">
        Share of postings asking for a skill (demand) against the share of your {data.total_students} students who list it (supply).
        A positive gap means the market wants it more than students have it.
      </p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Skill</th><th className="num">Demand</th><th className="num">Supply</th><th className="num">Gap</th></tr></thead>
          <tbody>
            {data.skills.map((s) => (
              <tr key={s.skill}>
                <td>{s.skill}</td>
                <td className="num">{s.demand_pct}% <small>({s.jobs} jobs)</small></td>
                <td className="num">{s.supply_pct}% <small>({s.students})</small></td>
                <td className={`num ${s.gap_pct > 0 ? "gap-pos" : "gap-neg"}`}>{s.gap_pct > 0 ? "+" : ""}{s.gap_pct} pts</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.trend.length > 0 && <><h3>Weekly demand for the biggest gaps</h3><TrendChart points={data.trend} /></>}
    </section>
  );
}

function CurriculumView() {
  const [scope] = useScope();
  const { data, error, loading, reload } = useAsync(() => api.curriculum({ scope }), [scope]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <>
      <div className="tiles">
        <div className="tile"><strong>{data.alignment_pct}%</strong><span>of requested skills are taught</span></div>
        <div className="tile"><strong>{data.total_jobs_with_skills}</strong><span>postings with skills</span></div>
      </div>
      <section className="card">
        <h2>By course</h2>
        <p className="muted">How many active postings ask for at least one skill the course teaches. The course list lives in <code>curriculum.yaml</code>.</p>
        <BarList rows={data.courses.map((c) => ({ label: c.course, value: c.jobs_pct, note: `(${c.jobs_mentioning} jobs)` }))} unit="%" max={100} />
      </section>
      <section className="card">
        <h2>In demand, but not in the curriculum</h2>
        {data.uncovered_skills.length === 0 ? <p>Every requested skill is covered.</p> : <BarList rows={data.uncovered_skills.map((s) => ({ label: s.skill, value: s.jobs }))} />}
      </section>
    </>
  );
}

export function AnalyticsPage() {
  const { user } = useAuth();
  const admin = user?.role === "admin";
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="skills" replace />} />
        <Route path="skills" element={<SkillsView />} />
        <Route path="companies" element={<CompaniesView />} />
        <Route path="skill-gap" element={admin ? <SkillGapView /> : <Navigate to="../skills" replace />} />
        <Route path="curriculum" element={admin ? <CurriculumView /> : <Navigate to="../skills" replace />} />
      </Route>
    </Routes>
  );
}
