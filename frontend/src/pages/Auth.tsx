import { useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { Brand } from "../components/Layout";
import { RESUME_ACCEPT, fileSize, resumeProblem } from "../components/ResumeUpload";
import { useAuth } from "../lib/auth";
import { parseList } from "../lib/format";

function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="auth">
      <Brand />
      <div className="auth-card">
        <div className="auth-bar">{title}</div>
        {children}
      </div>
    </div>
  );
}

function useSubmit(action: () => Promise<void>) {
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    setBusy(true);
    try {
      await action();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return { error, busy, onSubmit };
}

/** Optional resume picker. The file only lives in the form's state: nothing is uploaded yet. */
function ResumeField({ file, onChange }: { file: File | null; onChange: (file: File | null) => void }) {
  const [error, setError] = useState<string>();
  function pick(e: ChangeEvent<HTMLInputElement>) {
    const chosen = e.target.files?.[0];
    if (!chosen) return; // dialog cancelled
    const problem = resumeProblem(chosen);
    setError(problem);
    if (problem) e.target.value = ""; // so the same file can be picked again after fixing it
    onChange(problem ? null : chosen);
  }
  return (
    <>
      <div className="stack">
        {file ? (
          <div className="resume-file">
            <Icon name="file" size={20} />
            <span className="resume-meta">
              <strong>{file.name}</strong>
              <small>{fileSize(file.size)}</small>
            </span>
            <button type="button" className="btn small ghost" onClick={() => onChange(null)} aria-label={`Remove ${file.name}`}>
              Remove
            </button>
          </div>
        ) : (
          <label>
            <span>Resume <small>(optional · PDF or DOCX, up to 5 MB)</small></span>
            <input type="file" accept={RESUME_ACCEPT} onChange={pick} />
          </label>
        )}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
    </>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { error, busy, onSubmit } = useSubmit(async () => {
    await login(email, password);
    navigate(from, { replace: true });
  });
  return (
    <AuthShell title="Welcome back">
      <form className="auth-body" onSubmit={onSubmit}>
        <h1>Sign in</h1>
        <p className="lead">Pick up where you left off: new matches are waiting.</p>
        <div className="stack">
          <label>
            <span>Email</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </label>
          <label>
            <span>Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
          </label>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn primary block" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="alt">
          New here? <Link to="/register">Create an account</Link>
        </p>
      </form>
    </AuthShell>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [f, setF] = useState({ name: "", email: "", password: "", branch: "", cgpa: "", grad_year: String(new Date().getFullYear() + 1), skills: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  // Kept apart from `f`, which holds only strings. Not sent with the registration.
  const [resume, setResume] = useState<File | null>(null);
  const { error, busy, onSubmit } = useSubmit(async () => {
    await register({
      name: f.name.trim(),
      email: f.email.trim(),
      password: f.password,
      branch: f.branch.trim() || undefined,
      cgpa: f.cgpa ? Number(f.cgpa) : undefined,
      grad_year: Number(f.grad_year),
      skills: parseList(f.skills),
    });
    navigate("/", { replace: true });
  });
  return (
    <AuthShell title="Sign up">
      <form className="auth-body" onSubmit={onSubmit}>
        <h1>Create your account</h1>
        <p className="lead">Tell us what you know, and we will rank jobs by how well they fit.</p>
        <div className="stack">
          <label><span>Name</span><input value={f.name} onChange={set("name")} required autoComplete="name" /></label>
          <label><span>Email</span><input type="email" value={f.email} onChange={set("email")} required autoComplete="email" /></label>
          <label>
            <span>Password <small>(at least 8 characters)</small></span>
            <input type="password" value={f.password} onChange={set("password")} required minLength={8} autoComplete="new-password" />
          </label>
        </div>
        <div className="stack row">
          <label><span>Branch</span><input value={f.branch} onChange={set("branch")} placeholder="CSE" /></label>
          <label><span>CGPA</span><input type="number" step="0.01" min="0" max="10" value={f.cgpa} onChange={set("cgpa")} /></label>
          <label><span>Graduation year</span><input type="number" min="2000" max="2100" value={f.grad_year} onChange={set("grad_year")} required /></label>
        </div>
        <div className="stack">
          <label>
            <span>Skills <small>(comma separated)</small></span>
            <input value={f.skills} onChange={set("skills")} placeholder="python, sql, react" />
          </label>
        </div>
        <ResumeField file={resume} onChange={setResume} />
        {error &&<p className="form-error" role="alert">{error}</p>}
        <button className="btn primary block" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
        <p className="alt">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </AuthShell>
  );
}
