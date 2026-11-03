from functools import lru_cache
from datetime import date

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Job, Match, Students


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


def embed(texts: list[str]) -> list[list[float]]:
    return get_model().encode(texts, normalize_embeddings=True).tolist()


def job_text(title: str, skills: list[str] | None, description: str | None) -> str:
    return f"{title}. Skills: {', '.join(skills or [])}. {(description or '')[:500]}"


def student_text(skills: list[str] | None, branch: str | None) -> str:
    return f"Skills: {', '.join(skills or [])}. Branch: {branch or ''}."


def is_eligible(student: Students, job: Job) -> bool:
    if job.deadline_at and job.deadline_at < date.today():
        return False
    if job.min_cgpa is not None and (student.cgpa is None or student.cgpa < job.min_cgpa):
        return False
    if job.allowed_branches:
        if (student.branch or "").lower() not in [branch.lower() for branch in job.allowed_branches]:
            return False
    if job.allowed_grads and student.grad_year not in job.allowed_grads:
        return False
    return True


def similarity_score(student_vec: list[float] | None, job_vec: list[float] | None) -> float | None:
    if student_vec is None or job_vec is None:
        return None
    score = float(np.dot(student_vec, job_vec))
    return max(0.0, min(100.0, (score - 0.15) / (0.6 - 0.15) * 100))


def compute_matches(student: Students, db: Session) -> list[tuple[Job, float]]:
    jobs = db.scalars(select(Job).where(Job.is_active.is_(True))).all()
    eligible_jobs = [job for job in jobs if is_eligible(student, job)]
    if not eligible_jobs:
        return []

    if student.embedding is None:
        student.embedding = embed([student_text(student.skills, student.branch)])[0]

    jobs_without_embeddings = [job for job in eligible_jobs if job.embedding is None]
    if jobs_without_embeddings:
        vectors = embed(
            [job_text(job.title, job.necessary_skills, job.description) for job in jobs_without_embeddings]
        )
        for job, vector in zip(jobs_without_embeddings, vectors, strict=True):
            job.embedding = vector

    results = []
    for job in eligible_jobs:
        score = similarity_score(student.embedding, job.embedding)
        if score is not None:
            results.append((job, score))
    results.sort(key=lambda result: result[1], reverse=True)
    return results


def save_matches(student: Students, results, db: Session) -> None:
    existing = {match.job_id: match for match in db.scalars(select(Match).where(Match.student_id == student.id))}
    for job, score in results:
        if job.id in existing:
            existing[job.id].score = score
        else:
            db.add(Match(student_id=student.id, job_id=job.id, score=score))
