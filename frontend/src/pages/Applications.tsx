import { useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { api } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import type { Application, ApplicationStatus } from "../lib/types";

const STATUSES: ApplicationStatus[] = ["saved", "applied", "assessment", "interview", "offer", "rejected", "withdrawn"];

export function ApplicationsPage() {
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "all">("all");
  const { data, error, loading, reload } = useAsync(() => api.applications(statusFilter === "all" ? undefined : statusFilter), [statusFilter]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [errorMessage, setErrorMessage] = useState<string>();
  const [busyId, setBusyId] = useState<number>();

  async function update(application: Application, values: { status?: ApplicationStatus; notes?: string }) {
    setBusyId(application.id);
    setErrorMessage(undefined);
    try {
      await api.updateApplication(application.id, values);
      reload();
    } catch (err) {
      setErrorMessage((err as Error).message);
    } finally {
      setBusyId(undefined);
    }
  }

  async function remove(application: Application) {
    if (!window.confirm("Remove this job from your application tracker?")) return;
    setBusyId(application.id);
    setErrorMessage(undefined);
    try {
      await api.deleteApplication(application.id);
      reload();
    } catch (err) {
      setErrorMessage((err as Error).message);
    } finally {
      setBusyId(undefined);
    }
  }

  return (
    <>
      <section className="page-head">
        <h1>My applications</h1>
        <p className="lead">Track saved jobs and follow each application through your hiring pipeline.</p>
      </section>
      <label className="field application-filter">
        Filter by status
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as ApplicationStatus | "all")}>
          <option value="all">All applications</option>
          {STATUSES.map((status) => <option key={status} value={status}>{status.replace("_", " ")}</option>)}
        </select>
      </label>
      {loading && !data && <Loading label="Loading your applications…" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {errorMessage && <p className="form-error" role="alert">{errorMessage}</p>}
      {data && (data.length === 0 ? (
        <EmptyState title="No jobs tracked yet">Open a job and choose “Save to applications” to start tracking it.</EmptyState>
      ) : (
        <div className="application-list">
          {data.map((application) => (
            <article className="card application-card" key={application.id}>
              <div className="application-head">
                <h2><Link to={`/jobs/${application.job_id}`}>Job #{application.job_id}</Link></h2>
                <label className="field">
                  Status
                  <select
                    value={application.status}
                    disabled={busyId === application.id}
                    onChange={(event) => void update(application, { status: event.target.value as ApplicationStatus })}
                  >
                    {STATUSES.map((status) => <option key={status} value={status}>{status.replace("_", " ")}</option>)}
                  </select>
                </label>
              </div>
              <p className="muted">Last updated {new Date(application.updated_at).toLocaleDateString()}</p>
              <label className="field">
                Notes
                <textarea
                  maxLength={5000}
                  value={notes[application.id] ?? application.notes ?? ""}
                  onChange={(event) => setNotes({ ...notes, [application.id]: event.target.value })}
                  rows={3}
                />
              </label>
              <div className="application-actions">
                <button
                  type="button"
                  className="btn small"
                  disabled={busyId === application.id}
                  onClick={() => void update(application, { notes: notes[application.id] ?? application.notes ?? "" })}
                >
                  Save notes
                </button>
                <button type="button" className="btn small ghost" disabled={busyId === application.id} onClick={() => void remove(application)}>
                  Remove
                </button>
              </div>
            </article>
          ))}
        </div>
      ))}
    </>
  );
}
