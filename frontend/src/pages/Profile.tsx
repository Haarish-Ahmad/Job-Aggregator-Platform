import { useState, type FormEvent } from "react";
import { Loading } from "../components/States";
import { useAuth } from "../lib/auth";
import { parseList } from "../lib/format";
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
      <h1>Your profile</h1>
      <p className="lead">{user.name} · {user.email}{user.role === "admin" && " · admin"}</p>
      <form className="card form" onSubmit={save}>
        <div className="row">
          <label>Branch<input value={f.branch} onChange={set("branch")} placeholder="CSE" /></label>
          <label>CGPA<input type="number" step="0.01" min="0" max="10" value={f.cgpa} onChange={set("cgpa")} /></label>
          <label>Graduation year<input type="number" min="2000" max="2100" value={f.grad_year} onChange={set("grad_year")} required /></label>
        </div>
        <label>Skills <small>(comma separated)</small><input value={f.skills} onChange={set("skills")} placeholder="python, sql, react" /></label>
        <label>Resume link<input type="url" value={f.resume_link} onChange={set("resume_link")} placeholder="https://…" /></label>
        <button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
      </form>

      <section className="card">
        <h2>Email alerts</h2>
        <p>Get one email when new jobs match your profile well (60% or more of the required skills). No emails are sent unless you switch this on.</p>
        <label className="check">
          <input type="checkbox" checked={user.alerts_enabled} disabled={alertBusy} onChange={(e) => toggleAlerts(e.target.checked)} />
          Email me about new matches at {user.email}
        </label>
      </section>

      {status && <p className={status.kind === "ok" ? "form-ok" : "form-error"} role={status.kind === "ok" ? "status" : "alert"}>{status.text}</p>}
    </>
  );
}
