import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { parseList } from "../lib/format";

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
    <div className="auth">
      <form className="card" onSubmit={onSubmit}>
        <h1>Sign in</h1>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="alt">
          New here? <Link to="/register">Create an account</Link>
        </p>
      </form>
    </div>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [f, setF] = useState({ name: "", email: "", password: "", branch: "", cgpa: "", grad_year: String(new Date().getFullYear() + 1), skills: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
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
    <div className="auth">
      <form className="card" onSubmit={onSubmit}>
        <h1>Create your account</h1>
        <label>Name<input value={f.name} onChange={set("name")} required autoComplete="name" /></label>
        <label>Email<input type="email" value={f.email} onChange={set("email")} required autoComplete="email" /></label>
        <label>
          Password <small>(at least 8 characters)</small>
          <input type="password" value={f.password} onChange={set("password")} required minLength={8} autoComplete="new-password" />
        </label>
        <div className="row">
          <label>Branch<input value={f.branch} onChange={set("branch")} placeholder="CSE" /></label>
          <label>CGPA<input type="number" step="0.01" min="0" max="10" value={f.cgpa} onChange={set("cgpa")} /></label>
          <label>Graduation year<input type="number" min="2000" max="2100" value={f.grad_year} onChange={set("grad_year")} required /></label>
        </div>
        <label>
          Skills <small>(comma separated)</small>
          <input value={f.skills} onChange={set("skills")} placeholder="python, sql, react" />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn primary" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
        <p className="alt">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
