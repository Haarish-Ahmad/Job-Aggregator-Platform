from sqlalchemy import text,select,func,update
from sqlalchemy.orm import selectinload
from models import Companies,Job,Students,Match
from datetime import timedelta,date

def topskills(db,limit):
    rows=db.execute(
        text("""SELECT lower(trim(skill)) as Skill,COUNT(*) as jobs
        FROM job_postings,
        unnest(necessary_skills) as skill
        WHERE is_active AND trim(skill) <> ''
        GROUP BY 1
        ORDER BY jobs DESC
        LIMIT :limit""")
    ,{"limit":limit}
    ).all()
    return [{"skill":r.skill,"jobs":r.jobs}for r in rows]

def top_postings(db,limit):
    rows=db.execute(
        text("""
          SELECT lower(trim(title)) as job_post,COUNT(*) AS no_of_postings
          FROM job_postings
          WHERE is_active
          GROUP BY job_post
          ORDER BY no_of_postings DESC
          LIMIT :limit
        """),{"limit":limit}).all()
    return [r.job_post for r in rows]

def deactivate_expired(db)->int:
    res=db.execute(update(Job).where(Job.is_active.is_(True),Job.deadline_at.is_not(None),Job.deadline_at<date.today()).values(is_active=False))
    db.commit()
    return res.rowcount

def general_stats(db):
    companies=db.scalar(select(func.count()).select_from(Companies))
    active_jobs_count=db.scalar(select(func.count()).select_from(Job).where(Job.is_active.is_(True)))
    students=db.scalar(select(func.count()).select_from(Students).where(Students.role=="student"))
    jobs_this_week=db.scalars(select(Job).where(Job.scraped_at>=func.now()-timedelta(days=7)).order_by(Job.scraped_at.desc()).limit(50)).all()
    active_jobs=db.scalars(select(Job).where(Job.is_active.is_(True)).limit(50)).all()
    average_match=float(db.scalar(select(func.avg(Match.score)).select_from(Match)) or 0)
    return companies,active_jobs,jobs_this_week,average_match,students,active_jobs_count

def get_early_jobs(db, job_ids=None, limit=50):
    EARLY_DAYS=10
    q=select(Job).options(selectinload(Job.company)).where(Job.is_active.is_(True),
                           Job.scraped_at>=func.now()-timedelta(days=EARLY_DAYS))
    if job_ids is not None:
        q=q.where(Job.id.in_(job_ids))
    return db.scalars(q.order_by(Job.scraped_at.desc()).limit(limit)).all()

def get_dontapply_jobs(db):
    dontapply_jobs=db.scalars(select(Job).where(Job.is_active.is_(True),Job.scraped_at<func.now()-timedelta(days=10)).order_by(Job.scraped_at.asc()).limit(50)).all()
    return dontapply_jobs