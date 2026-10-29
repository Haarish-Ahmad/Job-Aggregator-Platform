from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import Job,Match,Students

def is_eligible(student:Students,job:Job)->bool:
    if job.deadline_at and job.deadline_at<date.today():
        return False
    if job.min_cgpa is not None and (student.cgpa is None or student.cgpa<job.min_cgpa):
        return False
    if job.allowed_branches:
        if (student.branch or "").lower() not in [b.lower() for b in job.allowed_branches]:
            return False
    if job.allowed_grads and student.grad_year not in job.allowed_grads:
        return False
    return True

def skill_score(student:Students,job:Job)->float:
    required={s.lower() for s in job.necessary_skills}
    if not required:
        return 100.0
    have={s.lower() for s in student.skills}
    return round(len(required&have)/len(required)*100,1)

def compute_matches(student:Students,db:Session)->list[tuple[Job,float]]:
    jobs=db.scalars(select(Job).where(Job.is_active.is_(True))).all()
    results=[(j,skill_score(student,j)) for j in jobs if is_eligible(student,j)]
    results.sort(key=lambda r:r[1],reverse=True)
    return results

def save_matches(student:Students,results,db:Session)->None:
    existing={m.job_id:m for m in db.scalars(select(Match).where(Match.student_id==student.id))}
    for job,score in results:
        if job.id in existing:
            existing[job.id].score=score
        else:
            db.add(Match(student_id=student.id,job_id=job.id,score=score))