import type { Job, Student } from "../lib/types";

// Built from local parts so tests behave the same in every time zone.
export const NOW = new Date(2026, 9, 18, 12, 0, 0);

export function job(overrides: Partial<Job> = {}): Job {
  return {
    id: 1, company_id: 1, company_name: "Acme Corp", title: "Python Developer", description: "Build APIs.\nSecond line.",
    location: "Pune, India", job_type: "full_time", min_cgpa: null, allowed_branches: [], allowed_grads: [], necessary_skills: ["python", "sql"],
    apply_url: "https://acme.example/jobs/1", deadline_at: null, is_active: true, source: "shine", external_id: "1", is_remote: false,
    is_india: true, work_mode: null, posted_date: null, scraped_at: "2026-10-17T10:00:00", last_seen_at: "2026-10-18T06:00:00", updated_at: null,
    ...overrides,
  };
}

export function student(overrides: Partial<Student> = {}): Student {
  return { id: 1, name: "Asha", email: "asha@college.edu", branch: "CSE", cgpa: 8.5, grad_year: 2026, skills: ["python"], role: "student", resume_link: null, alerts_enabled: false, ...overrides };
}
