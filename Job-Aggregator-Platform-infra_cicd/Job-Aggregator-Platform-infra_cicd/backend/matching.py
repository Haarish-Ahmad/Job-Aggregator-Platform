from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import Job,Match,Students
from functools import lru_cache
import numpy as np

@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer("all-MiniLM-L6-v2")
    return model

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

def embed(texts:list[str])->list[list[float]]:
    embeddings=get_model().encode(texts,normalize_embeddings=True).tolist()
    return embeddings

def job_text(title,skills,description):
    return f"{title}. Skills: {', '.join(skills or [])}. {(description or '')[:500]}"

def student_text(skills, branch):
    return f"Skills:{', '.join(skills or [])}. Branch:{branch}."

def similarity_score(student_vec,job_vec)->float:
    low=0.15
    high=0.6
    if not student_vec or not job_vec:
        return None
    score=float(np.dot(student_vec,job_vec))
    return max(0.0,min(100.0,(score-low)/(high-low)*100))

def compute_matches(student:Students,db:Session)->list[tuple[Job,float]]:
    jobs=db.scalars(select(Job).where(Job.is_active.is_(True))).all()
    results=[]
    for j in jobs:
        if not is_eligible(student,j):
            continue
        s=similarity_score(student.embedding,j.embedding)
        if s is not None:          
            results.append((j,s))
    results.sort(key=lambda r:r[1],reverse=True)
    return results

def save_matches(student:Students,results,db:Session)->None:
    existing={m.job_id:m for m in db.scalars(select(Match).where(Match.student_id==student.id))}
    for job,score in results:
        m=existing.get(job.id)
        if m is None:
            db.add(Match(student_id=student.id,job_id=job.id,score=score))
        elif abs(m.score-score)>0.05:
            m.score=score  

           