import { Link } from "react-router-dom";
import { BarList } from "../components/charts";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { api } from "../lib/api";
import { safeUrl } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export function DashboardPage() {
  const { data, error, loading, reload } = useAsync(() => api.myStats(), []);
  if (loading && !data) return <Loading label="Loading your dashboard…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;

  return (
    <>
      <section className="page-head">
        <h1>Your job-search dashboard</h1>
        <p className="lead">Personalized recommendations based on your profile and matching jobs.</p>
      </section>
      <div className="tiles">
        <div className="tile"><strong>{data.matching_jobs}</strong><span>jobs matching your profile</span></div>
        <div className="tile"><strong>{data.apply_early.length}</strong><span>good-fit jobs to apply to early</span></div>
      </div>
      <section className="card">
        <h2>Apply early</h2>
        {data.apply_early.length === 0 ? <EmptyState title="No early-application recommendations">Keep your profile current and check again after more jobs are collected.</EmptyState> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Job</th><th>Company</th><th className="num">Match</th><th>Apply</th></tr></thead>
              <tbody>{data.apply_early.map((job) => {
                const url = safeUrl(job.apply_url);
                return <tr key={job.id}><td><Link to={`/jobs/${job.id}`}>{job.title}</Link></td><td>{job.company_name}</td><td className="num">{Math.round(job.score)}%</td><td>{url ? <a href={url} target="_blank" rel="noopener noreferrer">Apply</a> : "—"}</td></tr>;
              })}</tbody>
            </table>
          </div>
        )}
      </section>
      <div className="two">
        <section className="card"><h2>Popular job skills</h2><p className="muted">Most requested skills across active postings.</p>{data.top_skills.length ? <BarList rows={data.top_skills.map((item) => ({ label: item.skill, value: item.jobs }))} /> : <p className="muted">No skill data yet.</p>}</section>
        <section className="card"><h2>Skills to build</h2><p className="muted">Frequently requested skills missing from your profile.</p>{data.skill_gap.length ? <BarList rows={data.skill_gap.map((item) => ({ label: item.skill, value: item.jobs }))} /> : <p className="muted">No skill gaps found.</p>}</section>
      </div>
    </>
  );
}
