// Shapes returned by the backend (backend/schemas.py). Keep in sync.
export interface Student {
  id: number;
  name: string;
  email: string;
  branch: string | null;
  cgpa: number | null;
  grad_year: number | null;
  skills: string[];
  role: "student" | "admin" | string;
  resume_link: string | null;
  has_resume: boolean;
  alerts_enabled: boolean;
}

export interface Job {
  id: number;
  company_id: number;
  company_name: string | null;
  title: string;
  description: string | null;
  location: string | null;
  job_type: string | null;
  min_cgpa: number | null;
  allowed_branches: string[];
  allowed_grads: number[];
  necessary_skills: string[];
  apply_url: string | null;
  deadline_at: string | null;
  is_active: boolean;
  source: string | null;
  external_id: string | null;
  is_remote: boolean;
  is_india: boolean | null;
  work_mode: string | null;
  posted_date: string | null;
  scraped_at: string | null;
  last_seen_at: string | null;
  updated_at: string | null;
}

export interface MatchedJob {
  score: number;
  job: Job;
}

export type Scope = "all" | "india" | "remote" | "india_remote";
export type Sort = "newest" | "oldest" | "deadline" | "title";

export interface JobQuery {
  q?: string;
  job_type?: string;
  location?: string;
  skill?: string;
  grad_year?: number;
  source?: string;
  company_group?: string;
  scope?: Scope;
  sort?: Sort;
  hide_expired?: boolean;
  limit?: number;
  offset?: number;
}

export interface JobPage {
  jobs: Job[];
  total: number;
}

export interface SkillCount {
  skill: string;
  jobs: number;
}
export interface TrendPoint {
  week: string;
  skill: string;
  jobs: number;
}
export interface SkillsReport {
  top: SkillCount[];
  trend: TrendPoint[];
}
export interface SkillGapRow {
  skill: string;
  jobs: number;
  students: number;
  demand_pct: number;
  supply_pct: number;
  gap_pct: number;
}
export interface SkillGapReport {
  total_students: number;
  total_jobs_with_skills: number;
  skills: SkillGapRow[];
  trend: TrendPoint[];
}
export interface CompaniesReport {
  totals: { active_jobs: number; remote: number; india: number; companies: number };
  top_companies: { company: string; jobs: number; internships: number; last_seen: string | null }[];
  by_type: { type: string; jobs: number }[];
  by_source: { source: string; jobs: number }[];
  weekly: { week: string; jobs: number }[];
}
export interface CurriculumReport {
  total_jobs_with_skills: number;
  alignment_pct: number;
  courses: { course: string; jobs_mentioning: number; jobs_pct: number; skills: { skill: string; jobs: number }[] }[];
  uncovered_skills: SkillCount[];
}

export interface RegisterInput {
  name: string;
  email: string;
  password: string;
  branch?: string;
  cgpa?: number;
  grad_year: number;
  skills: string[];
}
export type ProfileUpdate = Partial<Pick<Student, "branch" | "cgpa" | "grad_year" | "skills" | "resume_link" | "alerts_enabled">>;

export type ApplicationStatus = "saved" | "applied" | "assessment" | "interview" | "offer" | "rejected" | "withdrawn";
export interface Application {
  id: number;
  job_id: number;
  status: ApplicationStatus;
  notes: string | null;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface ResumeParseResult {
  has_resume: boolean;
  skills: string[];
  new_skills: string[];
  cgpa: number | null;
  grad_year: number | null;
}
export interface Company {
  id: number;
  company_name: string;
  careers_url: string;
  description: string | null;
}
export interface MyStats {
  matching_jobs: number;
  apply_early: { id: number; title: string; company_name: string; apply_url: string | null; score: number }[];
  top_skills: SkillCount[];
  skill_gap: SkillCount[];
}
export interface AdminAnalytics {
  companies: number;
  active_jobs: Job[];
  active_jobs_count: number;
  jobs_this_week: Job[];
  average_match: number;
  topskill: SkillCount[];
  students: number;
  early_jobs: Job[];
  late_jobs: Job[];
  top_posting: string[];
}
