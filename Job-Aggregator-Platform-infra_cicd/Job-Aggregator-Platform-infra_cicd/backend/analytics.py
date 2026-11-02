from sqlalchemy import text,select,func,update
from sqlalchemy.orm import selectinload
from models import Companies,Job,Students,Match
from datetime import timedelta,date
from pathlib import Path
from curriculum import load_curriculum

_SCOPE_SQL={
    "all":"",
    "india":" AND is_india IS TRUE",
    "remote":" AND is_remote IS TRUE",
    "india_remote":" AND (is_india IS TRUE OR is_remote IS TRUE)",
}

def _scope_sql(scope):
    if scope not in _SCOPE_SQL:
        raise ValueError("Invalid scope")
    return _SCOPE_SQL[scope]

def skill_trend(db,scope, weeks):
    rows=db.execute(text(f"""
        SELECT to_char(date_trunc('week',scraped_at),'YYYY-MM-DD') AS week,
               lower(trim(skill)) AS skill,COUNT(*) AS jobs
        FROM job_postings,unnest(necessary_skills) AS skill
        WHERE is_active AND scraped_at>=now()-make_interval(weeks=>:weeks)
          AND trim(skill)<>''{_scope_sql(scope)}
        GROUP BY 1,2 ORDER BY 1,3 DESC
    """),{"weeks":weeks}).all()
    return [{"week":row.week,"skill":row.skill,"jobs":row.jobs} for row in rows]

def skills_report(db,scope,limit,weeks):
    rows=db.execute(text(f"""
        SELECT lower(trim(skill)) AS skill,COUNT(*) AS jobs
        FROM job_postings,unnest(necessary_skills) AS skill
        WHERE is_active AND trim(skill)<>''{_scope_sql(scope)}
        GROUP BY 1 ORDER BY jobs DESC,skill LIMIT :limit
    """),{"limit":limit}).all()
    return {"top":[{"skill":row.skill,"jobs":row.jobs} for row in rows],
            "trend":skill_trend(db,scope,weeks)}

def skill_gap_report(db,scope,limit,weeks):
    demand=skills_report(db,scope,limit,weeks)["top"]
    total_jobs=db.scalar(text(f"""
        SELECT COUNT(*) FROM job_postings
        WHERE is_active AND cardinality(necessary_skills)>0{_scope_sql(scope)}
    """)) or 0
    students=db.scalars(select(Students).where(Students.role=="student")).all()
    counts={}
    for student in students:
        for skill in {value.strip().lower() for value in (student.skills or []) if value.strip()}:
            counts[skill]=counts.get(skill,0)+1
    skills=[]
    for item in demand:
        supply=counts.get(item["skill"],0)
        demand_pct=(item["jobs"]/total_jobs*100) if total_jobs else 0
        supply_pct=(supply/len(students)*100) if students else 0
        skills.append({"skill":item["skill"],"jobs":item["jobs"],"students":supply,
                       "demand_pct":round(demand_pct,2),"supply_pct":round(supply_pct,2),
                       "gap_pct":round(demand_pct-supply_pct,2)})
    return {"total_students":len(students),"total_jobs_with_skills":total_jobs,
            "skills":skills,"trend":skill_trend(db,scope,weeks)}

def companies_report(db,scope,limit,weeks):
    scope_sql=_scope_sql(scope)
    totals=db.execute(text(f"""
        SELECT COUNT(*) FILTER (WHERE is_active) AS active_jobs,
               COUNT(*) FILTER (WHERE is_active AND is_remote) AS remote,
               COUNT(*) FILTER (WHERE is_active AND is_india) AS india,
               COUNT(DISTINCT company_id) FILTER (WHERE is_active) AS companies
        FROM job_postings WHERE is_active{scope_sql}
    """)).one()
    top=db.execute(text(f"""
        SELECT c.company_name AS company,COUNT(*) AS jobs,
               COUNT(*) FILTER (WHERE lower(coalesce(j.job_type,'')) LIKE '%%intern%%') AS internships,
               max(j.last_seen_at) AS last_seen
        FROM job_postings j JOIN company c ON c.id=j.company_id
        WHERE j.is_active{scope_sql.replace('is_','j.is_')}
        GROUP BY c.company_name ORDER BY jobs DESC,c.company_name LIMIT :limit
    """),{"limit":limit}).all()
    by_type=db.execute(text(f"""
        SELECT coalesce(nullif(lower(job_type),''),'unknown') AS type,COUNT(*) AS jobs
        FROM job_postings WHERE is_active{scope_sql}
        GROUP BY 1 ORDER BY jobs DESC,type
    """)).all()
    by_source=db.execute(text(f"""
        SELECT coalesce(nullif(lower(source),''),'unknown') AS source,COUNT(*) AS jobs
        FROM job_postings WHERE is_active{scope_sql}
        GROUP BY 1 ORDER BY jobs DESC,source
    """)).all()
    weekly=db.execute(text(f"""
        SELECT to_char(date_trunc('week',scraped_at),'YYYY-MM-DD') AS week,COUNT(*) AS jobs
        FROM job_postings WHERE scraped_at>=now()-make_interval(weeks=>:weeks){scope_sql}
        GROUP BY 1 ORDER BY 1
    """),{"weeks":weeks}).all()
    return {
        "totals":{"active_jobs":totals.active_jobs or 0,"remote":totals.remote or 0,
                  "india":totals.india or 0,"companies":totals.companies or 0},
        "top_companies":[{"company":row.company,"jobs":row.jobs,"internships":row.internships,
                          "last_seen":row.last_seen.isoformat() if row.last_seen else None} for row in top],
        "by_type":[{"type":row.type,"jobs":row.jobs} for row in by_type],
        "by_source":[{"source":row.source,"jobs":row.jobs} for row in by_source],
        "weekly":[{"week":row.week,"jobs":row.jobs} for row in weekly],
    }

def curriculum_report(db,scope,limit):
    jobs=db.execute(text(f"""
        SELECT necessary_skills FROM job_postings
        WHERE is_active AND cardinality(necessary_skills)>0{_scope_sql(scope)}
    """)).all()
    demand={}
    total=len(jobs)
    for row in jobs:
        for skill in {value.strip().lower() for value in row.necessary_skills or [] if value.strip()}:
            demand[skill]=demand.get(skill,0)+1
    courses=load_curriculum(Path(__file__).with_name("curriculum.yaml"))
    covered={skill for course in courses for skill in course["skills"]}
    course_rows=[]
    for course in courses:
        matched=[{"skill":skill,"jobs":demand.get(skill,0)} for skill in course["skills"] if demand.get(skill,0)]
        jobs_mentioning=len({
            index for index,row in enumerate(jobs)
            if any(skill in row.necessary_skills for skill in course["skills"])
        })
        course_rows.append({"course":course["name"],"jobs_mentioning":jobs_mentioning,
                            "jobs_pct":round(jobs_mentioning/total*100,2) if total else 0,
                            "skills":matched})
    uncovered=sorted(
        ({"skill":skill,"jobs":count} for skill,count in demand.items() if skill not in covered),
        key=lambda item:(-item["jobs"],item["skill"])
    )[:limit]
    covered_jobs=sum(1 for row in jobs if any(skill in covered for skill in row.necessary_skills or []))
    return {"total_jobs_with_skills":total,
            "alignment_pct":round(covered_jobs/total*100,2) if total else 0,
            "courses":course_rows,"uncovered_skills":uncovered}

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