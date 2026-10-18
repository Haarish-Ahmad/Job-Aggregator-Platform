"""Analytics endpoints: plain SQL aggregations over active job postings and student profiles.

Skills are stored lowercase (the ingest schema lowercases them). Cohort-level views (skill gap,
curriculum alignment) are admin-only; demand and company views need a login.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from config import get_settings
from curriculum import load_curriculum
from db import get_db
from deps import get_current_user, require_admin

router = APIRouter(prefix="/analytics", tags=["analytics"])

Scope = Literal["all", "india", "remote", "india_remote"]
_SCOPE_SQL = {
    "all": "TRUE",
    "india": "j.is_india IS TRUE",
    "remote": "j.is_remote IS TRUE",
    "india_remote": "(j.is_india IS TRUE OR j.is_remote IS TRUE)",
}
# Posting date when the source gave one, otherwise when we first stored it.
_WHEN = "COALESCE(j.posted_date::timestamp, j.scraped_at)"


def _rows(db: Session, sql: str, **params) -> list[dict]:
    stmt = text(sql)
    if "skills" in params:
        stmt = stmt.bindparams(bindparam("skills", expanding=False))
    return [dict(r._mapping) for r in db.execute(stmt, params)]


def _top_skills(db: Session, scope: str, limit: int | None) -> list[dict]:
    return _rows(
        db,
        f"""SELECT lower(trim(s)) AS skill, count(DISTINCT j.id) AS jobs
            FROM job_postings j, unnest(j.necessary_skills) AS s
            WHERE j.is_active AND {_SCOPE_SQL[scope]} AND trim(s) <> ''
            GROUP BY 1 ORDER BY jobs DESC, skill {'LIMIT :limit' if limit else ''}""",
        **({"limit": limit} if limit else {}),
    )


def _trend(db: Session, skills: list[str], weeks: int, scope: str) -> list[dict]:
    if not skills:
        return []
    return [
        {"week": r["week"].isoformat(), "skill": r["skill"], "jobs": r["jobs"]}
        for r in _rows(
            db,
            f"""SELECT date_trunc('week', {_WHEN})::date AS week, lower(trim(s)) AS skill, count(DISTINCT j.id) AS jobs
                FROM job_postings j, unnest(j.necessary_skills) AS s
                WHERE lower(trim(s)) = ANY(:skills) AND {_SCOPE_SQL[scope]}
                  AND {_WHEN} >= now() - make_interval(weeks => :weeks)
                GROUP BY 1, 2 ORDER BY 1, 2""",
            skills=skills, weeks=weeks,
        )
    ]


@router.get("/skills")
def skills_demand(limit: int = Query(20, ge=1, le=100), weeks: int = Query(12, ge=1, le=104), scope: Scope = "all",
                  user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Most demanded skills across active postings, plus a weekly trend for the top five."""
    top = _top_skills(db, scope, limit)
    return {"top": top, "trend": _trend(db, [t["skill"] for t in top[:5]], weeks, scope)}


@router.get("/skill-gap")
def skill_gap(limit: int = Query(25, ge=1, le=100), weeks: int = Query(12, ge=1, le=104), scope: Scope = "all",
              admin=Depends(require_admin), db: Session = Depends(get_db)):
    """Demand for each skill (share of postings) against how many students list it (share of students)."""
    total_students = db.scalar(text("SELECT count(*) FROM students WHERE role = 'student'")) or 0
    total_jobs = db.scalar(text(
        f"SELECT count(*) FROM job_postings j WHERE j.is_active AND {_SCOPE_SQL[scope]} AND cardinality(j.necessary_skills) > 0"
    )) or 0
    supply = {
        r["skill"]: r["students"]
        for r in _rows(db, """SELECT lower(trim(s)) AS skill, count(DISTINCT st.id) AS students
                              FROM students st, unnest(st.skills) AS s WHERE st.role = 'student' GROUP BY 1""")
    }
    rows = []
    for item in _top_skills(db, scope, limit):
        demand_pct = round(100 * item["jobs"] / total_jobs, 1) if total_jobs else 0.0
        students = supply.get(item["skill"], 0)
        supply_pct = round(100 * students / total_students, 1) if total_students else 0.0
        rows.append({"skill": item["skill"], "jobs": item["jobs"], "students": students,
                     "demand_pct": demand_pct, "supply_pct": supply_pct, "gap_pct": round(demand_pct - supply_pct, 1)})
    rows.sort(key=lambda r: (-r["gap_pct"], r["skill"]))
    return {"total_students": total_students, "total_jobs_with_skills": total_jobs, "skills": rows,
            "trend": _trend(db, [r["skill"] for r in rows[:5]], weeks, scope)}


@router.get("/companies")
def company_patterns(limit: int = Query(15, ge=1, le=100), weeks: int = Query(12, ge=1, le=104), scope: Scope = "all",
                     user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Who is hiring: top companies, mix by type and source, weekly posting volume."""
    where = f"j.is_active AND {_SCOPE_SQL[scope]}"
    return {
        "totals": _rows(db, f"""SELECT count(*) AS active_jobs, count(*) FILTER (WHERE j.is_remote) AS remote,
                                      count(*) FILTER (WHERE j.is_india) AS india, count(DISTINCT j.company_id) AS companies
                               FROM job_postings j WHERE {where}""")[0],
        "top_companies": _rows(db, f"""SELECT c.company_name AS company, count(*) AS jobs,
                                             count(*) FILTER (WHERE j.job_type = 'internship') AS internships,
                                             max(j.scraped_at) AS last_seen
                                      FROM job_postings j JOIN company c ON c.id = j.company_id
                                      WHERE {where} GROUP BY c.id ORDER BY jobs DESC, company LIMIT :limit""", limit=limit),
        "by_type": _rows(db, f"SELECT coalesce(j.job_type, 'unknown') AS type, count(*) AS jobs FROM job_postings j WHERE {where} GROUP BY 1 ORDER BY jobs DESC"),
        "by_source": _rows(db, f"SELECT coalesce(j.source, 'manual') AS source, count(*) AS jobs FROM job_postings j WHERE {where} GROUP BY 1 ORDER BY jobs DESC"),
        "weekly": [
            {"week": r["week"].isoformat(), "jobs": r["jobs"]}
            for r in _rows(db, f"""SELECT date_trunc('week', {_WHEN})::date AS week, count(*) AS jobs
                                  FROM job_postings j
                                  WHERE {_SCOPE_SQL[scope]} AND {_WHEN} >= now() - make_interval(weeks => :weeks)
                                  GROUP BY 1 ORDER BY 1""", weeks=weeks)
        ],
    }


@router.get("/curriculum")
def curriculum_alignment(scope: Scope = "all", admin=Depends(require_admin), db: Session = Depends(get_db)):
    """How much of what active postings ask for is taught, per course, from curriculum.yaml."""
    try:
        courses = load_curriculum(get_settings().curriculum_file)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"curriculum.yaml: {exc}") from exc
    demand = {r["skill"]: r["jobs"] for r in _top_skills(db, scope, None)}
    total_jobs = db.scalar(text(
        f"SELECT count(*) FROM job_postings j WHERE j.is_active AND {_SCOPE_SQL[scope]} AND cardinality(j.necessary_skills) > 0"
    )) or 0
    taught = {s for c in courses for s in c["skills"]}
    result = []
    for course in courses:
        matching = db.scalar(
            text(f"SELECT count(*) FROM job_postings j WHERE j.is_active AND {_SCOPE_SQL[scope]} AND j.necessary_skills && CAST(:skills AS varchar[])"),
            {"skills": course["skills"]},
        ) or 0
        result.append({
            "course": course["name"],
            "jobs_mentioning": matching,
            "jobs_pct": round(100 * matching / total_jobs, 1) if total_jobs else 0.0,
            "skills": [{"skill": s, "jobs": demand.get(s, 0)} for s in course["skills"]],
        })
    mentions = sum(demand.values())
    covered = sum(n for s, n in demand.items() if s in taught)
    return {
        "total_jobs_with_skills": total_jobs,
        "alignment_pct": round(100 * covered / mentions, 1) if mentions else 0.0,
        "courses": sorted(result, key=lambda c: -c["jobs_mentioning"]),
        "uncovered_skills": [{"skill": s, "jobs": n} for s, n in demand.items() if s not in taught][:15],
    }
