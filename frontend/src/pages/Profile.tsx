import { useState, type FormEvent } from "react";
import { Icon } from "../components/Icon";
import { ResumeUpload } from "../components/ResumeUpload";
import { Loading } from "../components/States";
import { useAuth } from "../lib/auth";
import { api } from "../lib/api";
import { initials, parseList } from "../lib/format";
import type { ProfileUpdate, Student } from "../lib/types";
import { useLocation } from "react-router-dom";

export function ProfilePage() {
  const { user } = useAuth();
  const location = useLocation();
  const resumeUploadError = (location.state as { resumeUploadError?: string } | null)?.resumeUploadError;
  // The form copies the profile into its own state once, so it must only mount after the profile has loaded.
  return user ? <ProfileForm user={user} resumeUploadError={resumeUploadError} /> : <Loading />;
}

function ProfileForm({ user, resumeUploadError }: { user: Student; resumeUploadError?: string }) {
  const { updateProfile } = useAuth();
  const [f, setF] = useState({
    branch: user?.branch ?? "",
    cgpa: user?.cgpa?.toString() ?? "",
    grad_year: user?.grad_year?.toString() ?? "",
    skills: (user?.skills ?? []).join(", "),
  });
  // Frontend only for now: never sent with the profile, gone on refresh.
  const [resume, setResume] = useState<File | null>(null);
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | undefined>(
    resumeUploadError ? { kind: "error", text: resumeUploadError } : undefined,
  );
  const [busy, setBusy] = useState(false);
  const [alertBusy, setAlertBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatus(undefined);
    try {
      const update: ProfileUpdate = {
        branch: f.branch.trim() || null,
        cgpa: f.cgpa === "" ? null : Number(f.cgpa),
        grad_year: Number(f.grad_year),
        skills: parseList(f.skills),
      };
      if (resume) {
        const parsed = await api.uploadResume(resume);
        update.skills = [...new Set([...(update.skills ?? []), ...parsed.skills])];
        if (parsed.cgpa !== null) update.cgpa = parsed.cgpa;
        if (parsed.grad_year !== null) update.grad_year = parsed.grad_year;
      }
      await updateProfile(update);
      setResume(null);
      setStatus({ kind: "ok", text: "Profile saved." });
    } catch (err) {
      setStatus({ kind: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }
  async function toggleAlerts(on: boolean) {
    setAlertBusy(true);
    setStatus(undefined);
    try {
      await updateProfile({ alerts_enabled: on });
      setStatus({ kind: "ok", text: on ? "Email alerts are on." : "Email alerts are off." });
    } catch (err) {
      setStatus({ kind: "error", text: (err as Error).message });
    } finally {
      setAlertBusy(false);
    }
  }
  async function downloadResume() {
    setStatus(undefined);
    try {
      const url = URL.createObjectURL(await api.downloadResume());
      const link = document.createElement("a");
      link.href = url;
      link.download = "resume.pdf";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setStatus({ kind: "error", text: (err as Error).message });
    }
  }

  return (
    <>
      <section className="page-head">
        <h1>Your profile</h1>
        <p className="lead">Matches and alerts use these details. Keep your skills current.</p>
      </section>
      <div className="profile-grid">
        <aside className="id-card">
          <span className="avatar big" aria-hidden="true">{initials(user.name).slice(0, 1)}</span>
          <strong>{user.name}</strong>
          <span className="muted">{user.email}</span>
          {user.role === "admin" && <span className="badge">admin</span>}
          <dl className="id-facts">
            <div><dt>Skills</dt><dd>{user.skills.length}</dd></div>
            <div><dt>Graduating</dt><dd>{user.grad_year ?? "–"}</dd></div>
            <div><dt>CGPA</dt><dd>{user.cgpa ?? "–"}</dd></div>
          </dl>
        </aside>

        <div className="profile-main">
          <form className="panel form" onSubmit={save}>
            <h2>Academic details</h2>
            <div className="row">
              <label className="field">Branch<input value={f.branch} onChange={set("branch")} placeholder="CSE" /></label>
              <label className="field">CGPA<input type="number" step="0.01" min="0" max="10" value={f.cgpa} onChange={set("cgpa")} /></label>
              <label className="field">Graduation year<input type="number" min="2000" max="2100" value={f.grad_year} onChange={set("grad_year")} required /></label>
            </div>
            <label className="field">Skills <small>(comma separated)</small><input value={f.skills} onChange={set("skills")} placeholder="python, sql, react" /></label>
            {user.has_resume && <button type="button" className="btn small" onClick={() => void downloadResume()}>Download saved resume</button>}
            <ResumeUpload file={resume} onChange={setResume} />
            <div>
              <button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
            </div>
          </form>

          <section className="panel">
            <h2>
              <Icon name="bell" size={20} /> Email alerts
            </h2>
            <p className="muted">Get one email when new jobs match your profile well (60% or more of the required skills). No emails are sent unless you switch this on.</p>
            <label className="switch">
              <input type="checkbox" role="switch" checked={user.alerts_enabled} disabled={alertBusy} onChange={(e) => toggleAlerts(e.target.checked)} />
              <span className="track" aria-hidden="true" />
              Email me about new matches at {user.email}
            </label>
          </section>

          {status && <p className={status.kind === "ok" ? "form-ok" : "form-error"} role={status.kind === "ok" ? "status" : "alert"}>{status.text}</p>}
        </div>
      </div>
    </>
  );
}
