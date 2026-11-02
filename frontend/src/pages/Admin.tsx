import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { BarList } from "../components/charts";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useAsync } from "../lib/useAsync";
import type { Job } from "../lib/types";

function AdminJobList({ title, jobs }: { title: string; jobs: Job[] }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {jobs.length ? (
        <ul className="admin-job-list">
          {jobs.map((job) => <li key={job.id}><Link to={`/jobs/${job.id}`}>{job.title}</Link><span>{job.company_name ?? "Unknown company"}</span></li>)}
        </ul>
      ) : <p className="muted">No postings in this group yet.</p>}
    </section>
  );
}

export function AdminPage() {
  const { user } = useAuth();
  const [form, setForm] = useState({ company_name: "", careers_url: "", description: "" });
  const [formError, setFormError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const analytics = useAsync(() => api.adminAnalytics(), []);
  const companies = useAsync(() => api.companyDirectory(), []);

  if (user?.role !== "admin") return <Navigate to="/jobs" replace />;
  async function addCompany(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(undefined);
    try {
      await api.createCompany({ ...form, description: form.description.trim() || null });
      setForm({ company_name: "", careers_url: "", description: "" });
      companies.reload();
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }
  if (analytics.loading && !analytics.data) return <Loading label="Loading admin analytics…" />;
  if (analytics.error) return <ErrorState error={analytics.error} onRetry={analytics.reload} />;
  if (!analytics.data) return null;
  const report = analytics.data;

  return (
    <>
      <section className="page-head">
        <h1>Admin dashboard</h1>
        <p className="lead">Platform-wide hiring activity and company directory management.</p>
      </section>
      <div className="tiles">
        <div className="tile"><strong>{report.companies}</strong><span>companies</span></div>
        <div className="tile"><strong>{report.active_jobs_count}</strong><span>active jobs</span></div>
        <div className="tile"><strong>{report.students}</strong><span>students</span></div>
        <div className="tile"><strong>{report.average_match.toFixed(1)}%</strong><span>average match</span></div>
      </div>
      <div className="two">
        <section className="card"><h2>Most requested skills</h2><BarList rows={report.topskill.map((item) => ({ label: item.skill, value: item.jobs }))} /></section>
        <section className="card"><h2>Top hiring companies</h2>{report.top_posting.length ? <ol>{report.top_posting.map((company) => <li key={company}>{company}</li>)}</ol> : <p className="muted">No hiring data yet.</p>}</section>
      </div>
      <div className="two">
        <AdminJobList title="Recently active jobs" jobs={report.active_jobs} />
        <AdminJobList title="Jobs added this week" jobs={report.jobs_this_week} />
      </div>
      <div className="two">
        <AdminJobList title="Apply early" jobs={report.early_jobs} />
        <AdminJobList title="Closing or late opportunities" jobs={report.late_jobs} />
      </div>
      <section className="card">
        <h2>Company directory</h2>
        <form className="form" onSubmit={(event) => void addCompany(event)}>
          <label className="field">Company name<input required value={form.company_name} onChange={(event) => setForm({ ...form, company_name: event.target.value })} /></label>
          <label className="field">Careers URL<input type="url" required value={form.careers_url} onChange={(event) => setForm({ ...form, careers_url: event.target.value })} /></label>
          <label className="field">Description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} rows={3} /></label>
          {formError && <p className="form-error" role="alert">{formError}</p>}
          <button className="btn primary" disabled={saving}>{saving ? "Adding…" : "Add company"}</button>
        </form>
        {companies.loading && !companies.data && <Loading label="Loading companies…" />}
        {companies.error && <ErrorState error={companies.error} onRetry={companies.reload} />}
        {companies.data && (companies.data.length ? <div className="table-wrap"><table><thead><tr><th>Company</th><th>Careers</th><th>Description</th></tr></thead><tbody>{companies.data.map((company) => <tr key={company.id}><td>{company.company_name}</td><td><a href={company.careers_url} target="_blank" rel="noopener noreferrer">{company.careers_url}</a></td><td>{company.description ?? "—"}</td></tr>)}</tbody></table></div> : <EmptyState title="No companies yet">Companies will appear here once they are added or jobs are ingested.</EmptyState>)}
      </section>
    </>
  );
}
