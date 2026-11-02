import { useState, type FormEvent } from "react";
import { Icon } from "../components/Icon";
import { Loading } from "../components/States";
import { useAuth } from "../lib/auth";
import { api } from "../lib/api";
import { initials, parseList } from "../lib/format";
import type { ResumeParseResult, Student } from "../lib/types";

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
  const [resumeFile, setResumeFile] = useState<File>();
  const [resumeBusy, setResumeBusy] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [resumeResult, setResumeResult] = useState<ResumeParseResult>();
  const [resumeStatus, setResumeStatus] = useState<{ kind: "ok" | "error"; text: string }>();
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
  async function uploadResume(e: FormEvent) {
    e.preventDefault();
    if (!resumeFile) return;
    setResumeBusy(true);
    setResumeStatus(undefined);
    try {
      const result = await api.uploadResume(resumeFile);
      setResumeResult(result);
      setResumeStatus({ kind: "ok", text: "Resume uploaded and parsed. Review the extracted details before saving your profile." });
    } catch (err) {
      setResumeStatus({ kind: "error", text: (err as Error).message });
    } finally {
      setResumeBusy(false);
    }
  }
  function useResumeDetails() {
    if (!resumeResult) return;
    setF({
      ...f,
      skills: parseList([...parseList(f.skills), ...resumeResult.skills].join(", ")).join(", "),
      cgpa: resumeResult.cgpa === null ? f.cgpa : String(resumeResult.cgpa),
      grad_year: resumeResult.grad_year === null ? f.grad_year : String(resumeResult.grad_year),
    });
  }
  async function downloadResume() {
    setDownloadBusy(true);
    setResumeStatus(undefined);
    try {
      const blob = await api.downloadResume();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "resume.pdf";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setResumeStatus({ kind: "error", text: (err as Error).message });
    } finally {
      setDownloadBusy(false);
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
              <label className="field">Graduation year<input type="number" min="2000" max="2040" value={f.grad_year} onChange={set("grad_year")} required /></label>
            </div>
            <label className="field">Skills <small>(comma separated)</small><input value={f.skills} onChange={set("skills")} placeholder="python, sql, react" /></label>
            <label className="field">Resume link<input type="url" value={f.resume_link} onChange={set("resume_link")} placeholder="https://…" /></label>
            <div>
              <button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
            </div>
          </form>

          <section className="panel">
            <h2>Resume</h2>
            <p className="muted">Upload a PDF up to 10 MB. The backend extracts skills, CGPA, and graduation year for you to review.</p>
            <form className="form" onSubmit={uploadResume}>
              <label className="field">Resume PDF<input type="file" accept="application/pdf,.pdf" onChange={(e) => setResumeFile(e.target.files?.[0])} /></label>
              <div className="row">
                <button className="btn primary" disabled={!resumeFile || resumeBusy}>{resumeBusy ? "Uploading…" : "Upload and parse"}</button>
                <button className="btn" type="button" disabled={downloadBusy} onClick={downloadResume}>{downloadBusy ? "Downloading…" : "Download current resume"}</button>
              </div>
            </form>
            {resumeStatus && <p className={resumeStatus.kind === "ok" ? "form-ok" : "form-error"} role={resumeStatus.kind === "ok" ? "status" : "alert"}>{resumeStatus.text}</p>}
            {resumeResult && (
              <div className="form">
                <p><strong>Detected skills:</strong> {resumeResult.skills.length ? resumeResult.skills.join(", ") : "None found"}</p>
                <p><strong>CGPA:</strong> {resumeResult.cgpa ?? "Not found"} · <strong>Graduation year:</strong> {resumeResult.grad_year ?? "Not found"}</p>
                <button className="btn" type="button" onClick={useResumeDetails}>Use extracted details in profile</button>
              </div>
            )}
          </section>

          <section className="panel">
            <h2>
              <Icon name="bell" size={20} /> Email alerts
            </h2>
            <p className="muted">Get email alerts for new jobs above the backend’s configured profile-match threshold. No emails are sent unless you switch this on.</p>
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
