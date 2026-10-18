import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { App } from "../App";
import { ApiError, api } from "../lib/api";
import { job, student } from "../test/fixtures";
import { renderAt } from "../test/render";
import { JobDetailPage, safeUrl } from "./JobDetail";
import { MatchesPage } from "./Matches";
import { ProfilePage } from "./Profile";

vi.mock("../lib/api", async (orig) => {
  const real = await orig<typeof import("../lib/api")>();
  return {
    ...real,
    api: Object.fromEntries(["me", "login", "register", "logout", "updateProfile", "jobs", "job", "matches", "skills", "skillGap", "companies", "curriculum"].map((k) => [k, vi.fn()])),
  };
});
const m = vi.mocked(api);

const signedIn = (overrides = {}) => m.me.mockResolvedValue(student(overrides));
const signedOut = () => m.me.mockRejectedValue(new ApiError(401, "Not Logged in"));

beforeEach(() => {
  Object.values(m).forEach((fn) => (fn as ReturnType<typeof vi.fn>).mockReset());
  m.jobs.mockResolvedValue({ jobs: [], total: 0 });
  m.matches.mockResolvedValue([]);
  signedIn(); // most tests are signed in; the auth tests call signedOut() themselves
});

describe("auth guard", () => {
  it("sends signed-out visitors to the sign-in page", async () => {
    signedOut();
    renderAt(<App />, "/matches");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
  it("shows the app to signed-in users, with their name in the header", async () => {
    signedIn();
    renderAt(<App />, "/");
    expect(await screen.findByRole("heading", { name: "Jobs & internships" })).toBeInTheDocument();
    expect(screen.getByText("Asha")).toBeInTheDocument();
  });
  it("sign-in shows the server's message on a wrong password", async () => {
    signedOut();
    m.login.mockRejectedValue(new ApiError(401, "Invalid user account or password"));
    renderAt(<App />, "/login");
    await userEvent.type(await screen.findByLabelText("Email"), "a@b.co");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid user account or password");
  });
  it("signs in and lands on the jobs page", async () => {
    signedOut();
    m.login.mockResolvedValue(student());
    renderAt(<App />, "/login");
    await userEvent.type(await screen.findByLabelText("Email"), "asha@college.edu");
    await userEvent.type(screen.getByLabelText("Password"), "Test@1234");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Jobs & internships" })).toBeInTheDocument();
    expect(m.login).toHaveBeenCalledWith("asha@college.edu", "Test@1234");
  });
  it("signs out", async () => {
    signedIn();
    m.logout.mockResolvedValue();
    renderAt(<App />, "/");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
  it("registers with parsed skills, then signs in", async () => {
    signedOut();
    m.register.mockResolvedValue(student());
    m.login.mockResolvedValue(student());
    renderAt(<App />, "/register");
    await userEvent.type(await screen.findByLabelText("Name"), "Asha");
    await userEvent.type(screen.getByLabelText("Email"), "asha@college.edu");
    await userEvent.type(screen.getByLabelText(/Password/), "Test@1234");
    await userEvent.type(screen.getByLabelText(/Skills/), "Python, SQL");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(m.register).toHaveBeenCalledWith(expect.objectContaining({ name: "Asha", skills: ["python", "sql"] })));
    expect(await screen.findByRole("heading", { name: "Jobs & internships" })).toBeInTheDocument();
  });
});

describe("job detail", () => {
  const open = () => renderAt(<Routes><Route path="/jobs/:id" element={<JobDetailPage />} /></Routes>, "/jobs/1");
  it("shows the job with an apply link that opens the original posting safely", async () => {
    m.job.mockResolvedValue(job({ deadline_at: "2099-01-01", min_cgpa: 7, allowed_grads: [2026, 2027] }));
    m.matches.mockResolvedValue([{ score: 80, job: job() }]);
    signedIn();
    open();
    expect(await screen.findByRole("heading", { name: "Python Developer" })).toBeInTheDocument();
    const apply = screen.getByRole("link", { name: /Apply on the original posting/ });
    expect(apply).toHaveAttribute("href", "https://acme.example/jobs/1");
    expect(apply).toHaveAttribute("target", "_blank");
    expect(apply).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(await screen.findByText("80% skills match")).toBeInTheDocument();
    expect(screen.getByText("2026, 2027")).toBeInTheDocument();
  });
  it("never turns a javascript: URL into a link", async () => {
    m.job.mockResolvedValue(job({ apply_url: "javascript:alert(1)" }));
    open();
    expect(await screen.findByText("No valid apply link was provided.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Apply/ })).not.toBeInTheDocument();
  });
  it("renders scraped descriptions as text, never as HTML", async () => {
    m.job.mockResolvedValue(job({ description: "<img src=x onerror=alert(1)><script>alert(2)</script>Hello" }));
    open();
    expect(await screen.findByText(/Hello/)).toBeInTheDocument();
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(document.querySelector(".description script")).toBeNull();
  });
  it("says so when the job is gone", async () => {
    m.job.mockRejectedValue(new ApiError(404, "job not found"));
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("doesn't exist");
  });
  it("still shows the job when the match score can't be loaded", async () => {
    m.job.mockResolvedValue(job());
    m.matches.mockRejectedValue(new ApiError(500, "boom"));
    open();
    expect(await screen.findByRole("heading", { name: "Python Developer" })).toBeInTheDocument();
    expect(screen.queryByText(/skills match/)).not.toBeInTheDocument();
  });
  it("flags postings the source no longer lists", async () => {
    m.job.mockResolvedValue(job({ is_active: false }));
    open();
    expect(await screen.findByText("No longer listed by the source")).toBeInTheDocument();
  });
  it("safeUrl only allows http(s)", () => {
    expect(safeUrl("https://a.com/x")).toBe("https://a.com/x");
    expect([safeUrl("javascript:alert(1)"), safeUrl("data:text/html,x"), safeUrl("not a url"), safeUrl(null)]).toEqual([null, null, null, null]);
  });
});

describe("matches", () => {
  const open = () => renderAt(<MatchesPage />);
  it("lists ranked matches with scores and asks the API for 0% jobs only on request", async () => {
    signedIn();
    m.matches.mockResolvedValue([{ score: 100, job: job({ id: 1 }) }, { score: 50, job: job({ id: 2, title: "Half" }) }]);
    open();
    expect(await screen.findByLabelText("100 percent match")).toBeInTheDocument();
    expect(screen.getByLabelText("50 percent match")).toBeInTheDocument();
    expect(m.matches).toHaveBeenLastCalledWith({ min_score: 0, include_unmatched: false });
    await userEvent.click(screen.getByLabelText(/Include jobs with 0%/));
    await waitFor(() => expect(m.matches).toHaveBeenLastCalledWith({ min_score: 0, include_unmatched: true }));
  });
  it("tells a student with no skills to fill in their profile", async () => {
    signedIn({ skills: [], cgpa: null });
    open();
    expect(await screen.findByText("No matches yet")).toBeInTheDocument();
    expect(screen.getByText(/Add your skills and CGPA/)).toBeInTheDocument();
  });
  it("shows an error with retry", async () => {
    signedIn();
    m.matches.mockRejectedValueOnce(new ApiError(500, "boom")).mockResolvedValueOnce([]);
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No matches yet")).toBeInTheDocument();
  });
});

describe("profile and alerts", () => {
  it("subscribes to email alerts", async () => {
    signedIn();
    m.updateProfile.mockResolvedValue(student({ alerts_enabled: true }));
    renderAt(<ProfilePage />);
    const box = await screen.findByLabelText(/Email me about new matches/);
    expect(box).not.toBeChecked();
    await userEvent.click(box);
    expect(m.updateProfile).toHaveBeenCalledWith({ alerts_enabled: true });
    expect(await screen.findByRole("status")).toHaveTextContent("Email alerts are on.");
  });
  it("saves profile edits with a parsed skill list", async () => {
    signedIn();
    m.updateProfile.mockResolvedValue(student());
    renderAt(<ProfilePage />);
    const skills = await screen.findByLabelText(/Skills/);
    await userEvent.clear(skills);
    await userEvent.type(skills, "Go, Rust, go");
    await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => expect(m.updateProfile).toHaveBeenCalledWith(expect.objectContaining({ skills: ["go", "rust"], grad_year: 2026 })));
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
  });
  it("shows the server's validation message", async () => {
    signedIn();
    m.updateProfile.mockRejectedValue(new ApiError(422, "cgpa: Input should be less than or equal to 10"));
    renderAt(<ProfilePage />);
    await userEvent.click(await screen.findByRole("button", { name: "Save profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cgpa");
  });
});

describe("analytics", () => {
  const skills = { top: [{ skill: "python", jobs: 30 }, { skill: "sql", jobs: 12 }], trend: [{ week: "2026-10-12", skill: "python", jobs: 5 }, { week: "2026-10-19", skill: "python", jobs: 9 }] };
  it("shows skills in demand with a trend chart; hides admin-only tabs from students", async () => {
    signedIn();
    m.skills.mockResolvedValue(skills);
    renderAt(<App />, "/analytics");
    expect(await screen.findByText("Most requested skills")).toBeInTheDocument();
    expect(screen.getAllByText("python").length).toBeGreaterThanOrEqual(2); // bar label + chart legend
    expect(screen.getByRole("img", { name: /Weekly postings for python/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Companies & hiring" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Skill gap" })).not.toBeInTheDocument();
    expect(m.skills).toHaveBeenCalledWith(expect.objectContaining({ scope: "india_remote" }));
  });
  it("sends a student who types the admin URL back to the public view", async () => {
    signedIn();
    m.skills.mockResolvedValue(skills);
    renderAt(<App />, "/analytics/skill-gap");
    expect(await screen.findByText("Most requested skills")).toBeInTheDocument();
    expect(m.skillGap).not.toHaveBeenCalled();
  });
  it("shows the skill gap to admins", async () => {
    signedIn({ role: "admin" });
    m.skillGap.mockResolvedValue({ total_students: 40, total_jobs_with_skills: 100, trend: [], skills: [{ skill: "docker", jobs: 30, students: 4, demand_pct: 30, supply_pct: 10, gap_pct: 20 }] });
    renderAt(<App />, "/analytics/skill-gap");
    expect(await screen.findByText("+20 pts")).toBeInTheDocument();
    expect(screen.getByText(/your 40 students/)).toBeInTheDocument();
  });
  it("has an empty state when there is no data", async () => {
    signedIn();
    m.skills.mockResolvedValue({ top: [], trend: [] });
    renderAt(<App />, "/analytics/skills");
    expect(await screen.findByText("No skills data yet")).toBeInTheDocument();
  });
  it("shows company patterns and an error state with retry", async () => {
    signedIn();
    m.companies.mockRejectedValueOnce(new ApiError(500, "boom")).mockResolvedValueOnce({
      totals: { active_jobs: 7, remote: 2, india: 5, companies: 3 }, top_companies: [{ company: "Acme", jobs: 4, internships: 1, last_seen: null }],
      by_type: [{ type: "full_time", jobs: 5 }], by_source: [{ source: "shine", jobs: 7 }], weekly: [{ week: "2026-10-12", jobs: 7 }],
    });
    renderAt(<App />, "/analytics/companies");
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Who is hiring")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("active postings")).toBeInTheDocument();
  });
  it("shows curriculum alignment to admins", async () => {
    signedIn({ role: "admin" });
    m.curriculum.mockResolvedValue({ total_jobs_with_skills: 50, alignment_pct: 62.5, courses: [{ course: "Databases", jobs_mentioning: 20, jobs_pct: 40, skills: [] }], uncovered_skills: [{ skill: "kubernetes", jobs: 9 }] });
    renderAt(<App />, "/analytics/curriculum");
    expect(await screen.findByText("62.5%")).toBeInTheDocument();
    expect(screen.getByText("Databases")).toBeInTheDocument();
    expect(screen.getByText("kubernetes")).toBeInTheDocument();
  });
});
