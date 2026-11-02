import type {
  CompaniesReport,
  CurriculumReport,
  Job,
  JobPage,
  JobQuery,
  MatchedJob,
  ProfileUpdate,
  RegisterInput,
  Scope,
  SkillGapReport,
  SkillsReport,
  Student,
} from "./types";

/** API base URL: runtime config (config.js) > build-time VITE_API_BASE > "/api". */
export function apiBase(): string {
  const base = window.__APP_CONFIG__?.apiBase ?? import.meta.env.VITE_API_BASE ?? "/api";
  return base.replace(/\/+$/, "");
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Turns FastAPI's error bodies ({"detail": "..."} or a list of validation errors) into one sentence. */
function messageFrom(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".") || "input"}: ${d.msg ?? "invalid"}`)
      .join("; ");
  }
  if (status === 401) return "Please sign in.";
  if (status === 403) return "You don't have access to this.";
  if (status >= 500) return "The server had a problem. Please try again.";
  return `Request failed (${status}).`;
}

async function request(path: string, init: RequestInit & { json?: unknown } = {}): Promise<Response> {
  const { json, headers, ...rest } = init;
  let resp: Response;
  try {
    resp = await fetch(`${apiBase()}${path}`, {
      credentials: "include",
      ...rest,
      headers: { Accept: "application/json", ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (!resp.ok) {
    let body: unknown = null;
    try {
      body = await resp.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, messageFrom(resp.status, body));
  }
  return resp;
}

async function getJson<T>(path: string): Promise<T> {
  return (await request(path)).json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "" && v !== false) sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => getJson<{ status: string }>("/health"),

  me: () => getJson<Student>("/me"),
  login: async (email: string, password: string) => (await request("/auth/login", { method: "POST", json: { email, password } })).json() as Promise<Student>,
  register: async (input: RegisterInput) => (await request("/auth/register", { method: "POST", json: input })).json() as Promise<Student>,
  logout: async () => {
    await request("/auth/logout", { method: "POST" });
  },
  updateProfile: async (update: ProfileUpdate) => (await request("/me/update", { method: "PATCH", json: update })).json() as Promise<Student>,

  async jobs(query: JobQuery): Promise<JobPage> {
    const resp = await request(`/jobs${qs({ ...query, hide_expired: query.hide_expired })}`);
    const jobs = (await resp.json()) as Job[];
    const header = resp.headers.get("X-Total-Count");
    return { jobs, total: header !== null && header !== "" ? Number(header) : jobs.length };
  },
  job: (id: number) => getJson<Job>(`/jobs/${id}`),
  matches: (opts: { min_score?: number; include_unmatched?: boolean } = {}) =>
    getJson<MatchedJob[]>(`/me/matches${qs({ min_score: opts.min_score || undefined, include_unmatched: opts.include_unmatched })}`),

  skills: (opts: { scope?: Scope; limit?: number; weeks?: number } = {}) => getJson<SkillsReport>(`/analytics/skills${qs(opts)}`),
  skillGap: (opts: { scope?: Scope; limit?: number; weeks?: number } = {}) => getJson<SkillGapReport>(`/analytics/skill-gap${qs(opts)}`),
  companies: (opts: { scope?: Scope; limit?: number; weeks?: number } = {}) => getJson<CompaniesReport>(`/analytics/companies${qs(opts)}`),
  curriculum: (opts: { scope?: Scope } = {}) => getJson<CurriculumReport>(`/analytics/curriculum${qs(opts)}`),
};
