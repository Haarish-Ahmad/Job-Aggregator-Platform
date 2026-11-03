"""Student recommendations and platform-wide admin summaries."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from analytics import top_skills
from db import get_db
from deps import get_current_user, require_admin
from matching import compute_matches
from models import Companies, Job, Match, Students
from schemas import JobOut

router = APIRouter(tags=["insights"])


def _job_rows(jobs: list[Job]) -> list[JobOut]:
    return [JobOut.model_validate(job) for job in jobs]


@router.get("/me/stats")
def student_stats(
    limit: int = Query(10, ge=1, le=50),
    user: Students = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scored = [(job, score) for job, score in compute_matches(user, db) if score >= 40]
    db.commit()
    score_by_id = {job.id: score for job, score in scored}
    mine = {skill.strip().lower() for skill in user.skills}
    wanted: dict[str, int] = {}
    for job, _ in scored:
        for skill in job.necessary_skills or []:
            normalized = skill.strip().lower()
            if normalized and normalized not in mine:
                wanted[normalized] = wanted.get(normalized, 0) + 1

    skill_gap = [
        {"skill": skill, "jobs": count}
        for skill, count in sorted(wanted.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]
    job_ids = list(score_by_id)
    early_jobs = (
        db.scalars(
            select(Job)
            .options(joinedload(Job.company))
            .where(Job.id.in_(job_ids))
            .order_by(Job.posted_date.desc().nulls_last(), Job.scraped_at.desc(), Job.id.desc())
            .limit(10)
        ).unique().all()
        if job_ids
        else []
    )
    return {
        "matching_jobs": len(scored),
        "apply_early": [
            {
                "id": job.id,
                "title": job.title,
                "company_name": job.company.company_name,
                "apply_url": job.apply_url,
                "score": score_by_id[job.id],
            }
            for job in early_jobs
        ],
        "top_skills": top_skills(db, "all", limit),
        "skill_gap": skill_gap,
    }


@router.get("/admin/analytics")
def admin_analytics(
    limit: int = Query(50, ge=1, le=100),
    admin: Students = Depends(require_admin),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    today = date.today()
    active_jobs = db.scalars(
        select(Job)
        .options(joinedload(Job.company))
        .where(Job.is_active.is_(True))
        .order_by(Job.scraped_at.desc(), Job.id.desc())
        .limit(limit)
    ).unique().all()
    jobs_this_week = db.scalars(
        select(Job)
        .options(joinedload(Job.company))
        .where(Job.scraped_at >= now - timedelta(days=7))
        .order_by(Job.scraped_at.desc(), Job.id.desc())
        .limit(limit)
    ).unique().all()
    early_jobs = db.scalars(
        select(Job)
        .options(joinedload(Job.company))
        .where(Job.is_active.is_(True), Job.posted_date >= today - timedelta(days=7))
        .order_by(Job.posted_date.desc(), Job.id.desc())
        .limit(limit)
    ).unique().all()
    late_jobs = db.scalars(
        select(Job)
        .options(joinedload(Job.company))
        .where(Job.is_active.is_(True), Job.deadline_at >= today, Job.deadline_at <= today + timedelta(days=7))
        .order_by(Job.deadline_at.asc(), Job.id.desc())
        .limit(limit)
    ).unique().all()
    top_posting = db.scalars(
        select(Companies.company_name)
        .join(Job, Job.company_id == Companies.id)
        .where(Job.is_active.is_(True))
        .group_by(Companies.id, Companies.company_name)
        .order_by(func.count(Job.id).desc(), func.lower(Companies.company_name))
        .limit(limit)
    ).all()
    return {
        "companies": db.scalar(select(func.count(Companies.id))) or 0,
        "active_jobs_count": db.scalar(select(func.count(Job.id)).where(Job.is_active.is_(True))) or 0,
        "students": db.scalar(select(func.count(Students.id)).where(Students.role == "student")) or 0,
        "average_match": float(db.scalar(select(func.avg(Match.score))) or 0),
        "topskill": top_skills(db, "all", limit),
        "active_jobs": _job_rows(active_jobs),
        "jobs_this_week": _job_rows(jobs_this_week),
        "early_jobs": _job_rows(early_jobs),
        "late_jobs": _job_rows(late_jobs),
        "top_posting": top_posting,
    }
