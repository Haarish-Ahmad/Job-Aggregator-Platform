import { useState, type FormEvent } from "react";
import { Icon } from "../components/Icon";
import { Loading } from "../components/States";
import { useAuth } from "../lib/auth";
import { initials, parseList } from "../lib/format";
import type { Student } from "../lib/types";

export function ProfilePage() {
  const { user } = useAuth();
  // The form copies the profile into its own state once, so it must only mount after the profile has loaded.
  return user ? <ProfileForm user={user} /> : <Loading />;
}

function ProfileForm({ user }: { user: Student }) {
  const { updateProfile } = useAuth();
  const [f, setF] = useState({
    branch: user?.branch ?? "",
    cgpa: user?.cgpa?.toString() ?? "",
    grad_year: user?.grad_year?.toString() ?? "",
    skills: (user?.skills ?? []).join(", "),
    resume_link: user?.resume_link ?? "",
  });
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string }>();
  const [busy, setBusy] = useState(false);
  const [alertBusy, setAlertBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setStatus(undefined);
    try {
      await updateProfile({
        branch: f.branch.trim() || null,
        cgpa: f.cgpa === "" ? null : Number(f.cgpa),
        grad_year: Number(f.grad_year),
        skills: parseList(f.skills),
        resume_link: f.resume_link.trim() || null,
      });
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
            <label className="field">Resume link<input type="url" value={f.resume_link} onChange={set("resume_link")} placeholder="https://…" /></label>
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
