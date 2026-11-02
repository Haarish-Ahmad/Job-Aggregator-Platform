from fastapi import FastAPI,Depends,HTTPException,Request,Header,Response,Query,BackgroundTasks
from sqlalchemy.orm import Session,joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select,func,update,text,or_
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from metrics import MetricsMiddleware
from db import get_db,engine
from starlette.middleware.sessions import SessionMiddleware
from models import Companies,Students,Job,Application
from werkzeug.security import generate_password_hash,check_password_hash
from schemas import CompanyDetails, Analytics, CompanyOut, StudentDetails, StudentOut, LoginDetails, StudentUpdate, JobOut, MyStats, ingestionResult, bulkjobs, MatchOut, RecordResult, ApplicationCreate, ApplicationUpdate, ApplicationOut
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import os
from analytics import general_stats,deactivate_expired,get_dontapply_jobs,get_early_jobs,top_postings,topskills
import secrets
from target_companies import offcampus_targets
from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from datetime import timedelta,date,datetime
from config import INGEST_TOKEN,ALERT_LOCK_ID,SECRET_KEY,RESUME_DIR,COOKIE_SECURE,CORS_ORIGINS
from matching import compute_matches, save_matches, embed,job_text, student_text
from alert import run_alerts
from pathlib import Path
import logging
from collections import Counter
from typing import Literal
from urllib.parse import urlsplit
import yaml
from resume import pdf_to_text,load_vocab,extract_cgpa,extract_grad_year,extract_skills

logger=logging.getLogger(__name__)
RESUME_PATH=Path(RESUME_DIR)
RESUME_PATH.mkdir(exist_ok=True)

app=FastAPI(title="Job Aggregator Platform",root_path=os.getenv("ROOT_PATH",""))
app.add_middleware(SessionMiddleware,secret_key=SECRET_KEY,
    max_age=60*60*12,same_site="lax",https_only=COOKIE_SECURE)
app.add_middleware(MetricsMiddleware)
app.add_middleware(CORSMiddleware,allow_origins=CORS_ORIGINS,allow_credentials=True,
    allow_methods=["*"],allow_headers=["*"],expose_headers=["X-Total-Count"])

def get_current_user(request:Request,db:Session=Depends(get_db)):
    student_id=request.session.get('student_id')
    if not student_id:
        raise HTTPException(status_code=401,detail='Not Logged in')
    student=db.get(Students,student_id)
    if not student:
        request.session.clear()
        raise HTTPException(status_code=401, detail="User not found")
    return student

def require_admin(user:Students=Depends(get_current_user)):
    if user.role!="admin":
        raise HTTPException(status_code=403,detail="Admin only can access!")
    return user

def ingest_auth(request:Request,x_ingest_token:str|None=Header(default=None),legacy_token:str|None=Header(default=None,alias="ingest-token"),db:Session=Depends(get_db)):
    token=x_ingest_token or legacy_token
    if token:
        if INGEST_TOKEN and secrets.compare_digest(token,INGEST_TOKEN):
            return "ingest-token"
        raise HTTPException(status_code=401,detail="Invalid ingest token")
    user=get_current_user(request,db)
    if user.role!="admin":
        raise HTTPException(status_code=403,detail="Admin only can access!")
    return user

def make_hash(company: str, title: str, location: str | None) -> str:
    raw = f"{company}|{title}|{location or ''}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()

def make_source_hash(source:str,external_id:str)->str:
    raw=f"{source}\0{external_id}"
    return hashlib.sha256(raw.encode()).hexdigest()

def job_alerts():
    with engine.connect() as lock:
        if not lock.scalar(text("select pg_try_advisory_lock(:k)"),{"k":ALERT_LOCK_ID}):
            print("alerts already running, skipping")
            return
        try:
            with Session(engine) as db:  
                deactivate_expired(db)
                print("emails sent:",run_alerts(db))
        finally:
            lock.scalar(text("select pg_advisory_unlock(:k)"),{"k":ALERT_LOCK_ID})

@app.get("/health")
def check_health(db:Session=Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503,detail="database unavailable") from None
    return {'status':'ok','db':'ok'}

@app.post("/company",response_model=CompanyOut,status_code=201,dependencies=[Depends(require_admin)])
def company_create(data:CompanyDetails,db:Session=Depends(get_db)):
    if db.scalars(select(Companies).where(func.lower(Companies.company_name)==data.company_name.lower())).first():
        raise HTTPException(status_code=409,detail="Company already exist")
    c=Companies(**data.model_dump())
    db.add(c)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409,detail="Company already there")
    db.refresh(c)
    return c

@app.get("/companies",response_model=list[CompanyOut],dependencies=[Depends(get_current_user)])
def list_company(db:Session=Depends(get_db)):
    return db.scalars(select(Companies)).all()

@app.post("/auth/register",response_model=StudentOut,status_code=201)
def student_register(data:StudentDetails,db:Session=Depends(get_db)):
    if db.scalars(select(Students).where(data.email==Students.email)).first():
        raise HTTPException(status_code=409,detail="Student Exists")
    password_hash=generate_password_hash(data.password)
    student=Students(**data.model_dump(exclude={"password"}),password_hash=password_hash,embedding=embed([student_text(data.skills,data.branch)])[0])
    db.add(student)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409,detail="Student Exists")
    db.refresh(student)
    return student

@app.post("/auth/login",response_model=StudentOut)    
def login(data: LoginDetails,request: Request,db:Session=Depends(get_db)):
    user=db.scalars(select(Students).where(data.email==Students.email)).first()
    if not user or not check_password_hash(user.password_hash,data.password):
        raise HTTPException(status_code=401,detail="Invalid user account or password")
    request.session["student_id"]=user.id
    return user

@app.post("/auth/logout")
def logout(request:Request):
    request.session.clear()
    return {"detail": "logged out"}

@app.get("/me", response_model=StudentOut)
def me(user:Students=Depends(get_current_user)):
    return user

@app.patch("/me/update",response_model=StudentOut)
def update_profile(data:StudentUpdate,user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    NOT_NULLABLE={"name","branch","grad_year","skills","alerts_enabled"}
    changes=data.model_dump(exclude_unset=True)
    for field,val in changes.items():
        if val is None and field in NOT_NULLABLE:
            raise HTTPException(status_code=422,detail=f"{field} cannot be null")
        setattr(user,field,val)
    if "skills" in changes or "branch" in changes:
        user.embedding=embed([student_text(user.skills,user.branch)])[0]
    db.commit()
    db.refresh(user)
    return user    

@app.post("/internal/jobs",response_model=ingestionResult,dependencies=[Depends(ingest_auth)])
def get_jobs(data:bulkjobs,db:Session=Depends(get_db)):
    inserted=updated=skipped=rejected=0
    results=[]
    for index,item in enumerate(data.jobs):
        error=None
        if not item.company_name or len(item.company_name)>100:
            error="company_name must contain 1-100 characters"
        elif not item.title or len(item.title)>255:
            error="title must contain 1-255 characters"
        elif not item.apply_url or len(item.apply_url)>500:
            error="apply_url must contain 1-500 characters"
        elif urlsplit(item.apply_url).scheme not in ("http","https") or not urlsplit(item.apply_url).netloc:
            error="apply_url must be a valid http:// or https:// URL"
        elif item.location is not None and len(item.location)>150:
            error="location must be at most 150 characters"
        elif item.job_type is not None and len(item.job_type)>30:
            error="job_type must be at most 30 characters"
        elif item.source is not None and len(item.source)>50:
            error="source must be at most 50 characters"
        elif item.external_id is not None and len(item.external_id)>255:
            error="external_id must be at most 255 characters"
        elif item.source_content_hash is not None and len(item.source_content_hash)>64:
            error="source_content_hash must be at most 64 characters"
        elif item.work_mode is not None and len(item.work_mode)>20:
            error="work_mode must be at most 20 characters"
        elif item.min_cgpa is not None and not 0<=item.min_cgpa<=10:
            error="min_cgpa must be between 0 and 10"
        elif (item.source is None)!=(item.external_id is None):
            error="source and external_id must be provided together"
        elif item.source is not None and (not item.source or not item.external_id):
            error="source and external_id cannot be empty"
        if error:
            rejected+=1
            results.append(RecordResult(index=index,status="rejected",reason=error))
            continue

        try:
            with db.begin_nested():
                company=db.scalars(select(Companies).where(
                    func.lower(Companies.company_name)==item.company_name.lower()
                )).first()
                if not company:
                    company=Companies(company_name=item.company_name,careers_url=item.apply_url,description=None)
                    db.add(company)
                    db.flush()

                legacy_hash=make_hash(item.company_name,item.title,item.location)
                identity_hash=make_source_hash(item.source,item.external_id) if item.source else legacy_hash
                if item.source and item.external_id:
                    existing=db.scalars(select(Job).where(
                        Job.source==item.source,Job.external_id==item.external_id
                    )).first()
                    if not existing:
                        existing=db.scalars(select(Job).where(
                            Job.content_hash==legacy_hash,Job.source.is_(None),Job.external_id.is_(None)
                        )).first()
                else:
                    existing=db.scalars(select(Job).where(Job.content_hash==legacy_hash)).first()

                if existing:
                    changed=(
                        existing.company_id!=company.id
                        or existing.title!=item.title
                        or existing.description!=item.description
                        or existing.location!=item.location
                        or existing.job_type!=item.job_type
                        or existing.min_cgpa!=item.min_cgpa
                        or existing.allowed_branches!=item.allowed_branches
                        or existing.allowed_grads!=item.allowed_grads
                        or existing.necessary_skills!=item.required_skills
                        or existing.apply_url!=item.apply_url
                        or existing.deadline_at!=item.deadline
                        or existing.source!=item.source
                        or existing.external_id!=item.external_id
                        or existing.source_content_hash!=item.source_content_hash
                        or existing.is_remote!=item.is_remote
                        or existing.is_india!=item.is_india
                        or existing.work_mode!=item.work_mode
                        or existing.posted_date!=item.posted_date
                    )
                    embedding_changed=(
                        existing.title!=item.title
                        or existing.description!=item.description
                        or existing.necessary_skills!=item.required_skills
                    )
                    existing.company_id=company.id
                    existing.title=item.title
                    existing.description=item.description
                    existing.location=item.location
                    existing.job_type=item.job_type
                    existing.min_cgpa=item.min_cgpa
                    existing.allowed_branches=item.allowed_branches
                    existing.allowed_grads=item.allowed_grads
                    existing.necessary_skills=item.required_skills
                    existing.apply_url=item.apply_url
                    existing.deadline_at=item.deadline
                    existing.source=item.source
                    existing.external_id=item.external_id
                    existing.source_content_hash=item.source_content_hash
                    existing.is_remote=item.is_remote
                    existing.is_india=item.is_india
                    existing.work_mode=item.work_mode
                    existing.posted_date=item.posted_date
                    existing.content_hash=identity_hash if item.source else legacy_hash
                    existing.last_seen_at=func.now()
                    existing.is_active=not (item.deadline and item.deadline<date.today())
                    if changed:
                        existing.updated_at=func.now()
                    if embedding_changed:
                        existing.embedding=embed([job_text(item.title,item.required_skills,item.description)])[0]
                    job_id=existing.id
                else:
                    job=Job(
                        company_id=company.id,
                        title=item.title,
                        description=item.description,
                        location=item.location,
                        job_type=item.job_type,
                        min_cgpa=item.min_cgpa,
                        allowed_branches=item.allowed_branches,
                        allowed_grads=item.allowed_grads,
                        necessary_skills=item.required_skills,
                        apply_url=item.apply_url,
                        content_hash=identity_hash if item.source else legacy_hash,
                        embedding=embed([job_text(item.title,item.required_skills,item.description)])[0],
                        deadline_at=item.deadline,
                        source=item.source,
                        external_id=item.external_id,
                        source_content_hash=item.source_content_hash,
                        is_remote=item.is_remote,
                        is_india=item.is_india,
                        work_mode=item.work_mode,
                        posted_date=item.posted_date,
                        is_active=not (item.deadline and item.deadline<date.today()),
                    )
                    db.add(job)
                    db.flush()
                    job_id=job.id
        except Exception:
            logger.exception("Job ingestion failed for record index %s",index)
            rejected+=1
            results.append(RecordResult(index=index,status="rejected",reason="record could not be saved"))
            continue

        if existing:
            if changed:
                updated+=1
                results.append(RecordResult(index=index,status="updated",job_id=job_id))
            else:
                skipped+=1
                results.append(RecordResult(index=index,status="unchanged",job_id=job_id))
        else:
            inserted+=1
            results.append(RecordResult(index=index,status="inserted",job_id=job_id))

    try:
        db.execute(update(Job).where(
            Job.is_active.is_(True),
            Job.deadline_at.is_not(None),
            Job.deadline_at<date.today(),
        ).values(is_active=False))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not commit job ingestion batch")
        raise HTTPException(status_code=500,detail="Could not save ingestion batch")
    return ingestionResult(inserted=inserted,updated=updated,skipped=skipped,rejected=rejected,results=results)

@app.post("/internal/maintenance/deactivate-stale",dependencies=[Depends(ingest_auth)])
def deactivate_stale_jobs(days:int=Query(14,ge=1,le=3650),db:Session=Depends(get_db)):
    cutoff=datetime.now()-timedelta(days=days)
    result=db.execute(update(Job).where(
        Job.is_active.is_(True),
        Job.source.is_not(None),
        Job.last_seen_at<cutoff,
    ).values(is_active=False))
    db.commit()
    return {"deactivated":result.rowcount or 0}

@app.get("/jobs",response_model=list[JobOut])  
def jobs(response:Response,q:str|None=None,company_id:int|None=None,job_type:str|None=None,active_only:bool=True,limit:int=Query(50,ge=1),offset:int=Query(0,ge=0),location:str|None=None,company:str|None=None,company_group:str|None=None,skill:str|None=None,grad_year:int|None=None,source:str|None=None,scope:Literal["all","india","remote","india_remote"]="all",hide_expired:bool=False,sort:Literal["newest","oldest","deadline","title"]="newest",user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    query=select(Job).join(Job.company).options(joinedload(Job.company))
    if q:
        query=query.where(or_(
            Job.title.ilike(_like(q),escape="\\"),
            Companies.company_name.ilike(_like(q),escape="\\"),
        ))
    if company_id:
        query=query.where(Job.company_id==company_id)
    if job_type:
        query=query.where(func.lower(Job.job_type)==job_type.lower())
    if location:
        query=query.where(Job.location.ilike(_like(location),escape="\\"))
    if company:
        query=query.where(Companies.company_name.ilike(_like(company),escape="\\"))
    if company_group:
        target=offcampus_targets.get(company_group)
        if target is None:
            raise HTTPException(status_code=400,detail="Invalid company group")
        query=query.where(func.lower(Companies.company_name).in_([name.lower() for name in target]))
    if active_only:
        query=query.where(Job.is_active.is_(True))
    if hide_expired:
        query=query.where(or_(Job.deadline_at.is_(None),Job.deadline_at>=date.today()))
    if source:
        query=query.where(Job.source==source)
    if scope=="india":
        query=query.where(Job.is_india.is_(True))
    elif scope=="remote":
        query=query.where(Job.is_remote.is_(True))
    elif scope=="india_remote":
        query=query.where(or_(Job.is_india.is_(True),Job.is_remote.is_(True)))
    ordering={
        "newest":(Job.scraped_at.desc(),Job.id.desc()),
        "oldest":(Job.scraped_at.asc(),Job.id.asc()),
        "deadline":(Job.deadline_at.asc().nulls_last(),Job.id.desc()),
        "title":(func.lower(Job.title).asc(),Job.id.asc()),
    }
    candidates=db.scalars(query.order_by(*ordering[sort])).unique().all()
    if skill:
        normalized_skill=skill.strip().casefold()
        candidates=[job for job in candidates if normalized_skill in {value.strip().casefold() for value in (job.necessary_skills or [])}]
    if grad_year is not None:
        candidates=[job for job in candidates if not job.allowed_grads or grad_year in job.allowed_grads]
    response.headers["X-Total-Count"]=str(len(candidates))
    return candidates[offset:offset+min(limit,100)]

def _like(value:str)->str:
    return "%"+value.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"

@app.get("/jobs/filter",response_model=list[JobOut])
def filter_jobs(input:str,user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    target=offcampus_targets.get(input)
    if target is None:
        raise HTTPException(status_code=400,detail="Invalid option")
    target_names=[name.lower() for name in target]
    return db.scalars(select(Job).join(Companies,Job.company_id==Companies.id).where(
        func.lower(Companies.company_name).in_(target_names),Job.is_active.is_(True)
    )).all()

@app.get("/jobs/{job_id}",response_model=JobOut,dependencies=[Depends(get_current_user)])
def get_job_with_id(job_id:int,db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job:
        raise HTTPException(status_code=404,detail="job not found")
    return job

@app.get("/me/applications",response_model=list[ApplicationOut])
def list_applications(status:Literal["saved","applied","assessment","interview","offer","rejected","withdrawn"]|None=None,user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    query=select(Application).where(Application.student_id==user.id)
    if status:
        query=query.where(Application.status==status)
    return db.scalars(query.order_by(Application.updated_at.desc(),Application.id.desc())).all()

@app.post("/me/applications",response_model=ApplicationOut,status_code=201)
def create_application(data:ApplicationCreate,user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    if not db.get(Job,data.job_id):
        raise HTTPException(status_code=404,detail="job not found")
    application=Application(
        student_id=user.id,
        job_id=data.job_id,
        status=data.status,
        notes=data.notes,
        applied_at=datetime.now() if data.status!="saved" else None,
    )
    db.add(application)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409,detail="Application already tracked for this job")
    db.refresh(application)
    return application

@app.patch("/me/applications/{application_id}",response_model=ApplicationOut)
def update_application(application_id:int,data:ApplicationUpdate,user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    application=db.scalars(select(Application).where(
        Application.id==application_id,Application.student_id==user.id
    )).first()
    if not application:
        raise HTTPException(status_code=404,detail="application not found")
    changes=data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422,detail="At least one field must be provided")
    if changes.get("status") is None and "status" in changes:
        raise HTTPException(status_code=422,detail="status cannot be null")
    for field,value in changes.items():
        setattr(application,field,value)
    if application.status!="saved" and application.applied_at is None:
        application.applied_at=datetime.now()
    application.updated_at=datetime.now()
    db.commit()
    db.refresh(application)
    return application

@app.delete("/me/applications/{application_id}",status_code=204)
def delete_application(application_id:int,user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    application=db.scalars(select(Application).where(
        Application.id==application_id,Application.student_id==user.id
    )).first()
    if not application:
        raise HTTPException(status_code=404,detail="application not found")
    db.delete(application)
    db.commit()
    return Response(status_code=204)

@app.get("/me/matches",response_model=list[MatchOut])
def get_matches(user:Students=Depends(get_current_user),min_score:float=0,db:Session=Depends(get_db)):
    result=compute_matches(user,db)
    save_matches(user,result,db)
    try:
      db.commit()
    except IntegrityError:
        db.rollback()
    return [{"score":s,"job":j} for j,s in result if s>=min_score]

@app.get("/admin/analytics",response_model=Analytics,dependencies=[Depends(require_admin)])
def all_analytics(limit:int=Query(50,ge=10,le=100),db:Session=Depends(get_db)):
    companies,active_jobs,jobs_this_week,average_match,students,active_jobs_count=general_stats(db)
    early_jobs=get_early_jobs(db)
    late_jobs=get_dontapply_jobs(db)
    topskill=topskills(db,limit)
    top_posting=top_postings(db,limit)

    return {'companies':companies,'active_jobs':active_jobs,'active_jobs_count':active_jobs_count,'jobs_this_week':jobs_this_week,'average_match':average_match,'students':students,'top_posting':top_posting,'topskill':topskill,'early_jobs':early_jobs,'late_jobs':late_jobs}

def _analytics_jobs(db:Session,scope:str,active_only:bool=True):
    query=select(Job).options(joinedload(Job.company))
    if active_only:
        query=query.where(Job.is_active.is_(True))
    if scope=="india":
        query=query.where(Job.is_india.is_(True))
    elif scope=="remote":
        query=query.where(Job.is_remote.is_(True))
    elif scope=="india_remote":
        query=query.where(or_(Job.is_india.is_(True),Job.is_remote.is_(True)))
    return db.scalars(query).unique().all()

def _skill_counts(jobs:list[Job])->Counter:
    counts=Counter()
    for job in jobs:
        counts.update({skill.strip().casefold() for skill in (job.necessary_skills or []) if skill.strip()})
    return counts

def _weekly_skill_trend(jobs:list[Job],skills:list[str],weeks:int)->list[dict]:
    start=date.today()-timedelta(weeks=weeks)
    trend=Counter()
    for job in jobs:
        posted=job.posted_date or job.scraped_at.date()
        if posted<start:
            continue
        week=posted-timedelta(days=posted.weekday())
        for skill in {value.strip().casefold() for value in (job.necessary_skills or []) if value.strip()}:
            if skill in skills:
                trend[(week,skill)]+=1
    return [{"week":week.isoformat(),"skill":skill,"jobs":count} for (week,skill),count in sorted(trend.items())]

def _validate_scope(scope:str)->str:
    if scope not in {"all","india","remote","india_remote"}:
        raise HTTPException(status_code=422,detail="Invalid scope")
    return scope

@app.get("/analytics/skills")
def skills_demand(limit:int=Query(20,ge=1,le=100),weeks:int=Query(12,ge=1,le=104),scope:Literal["all","india","remote","india_remote"]="all",user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    jobs=_analytics_jobs(db,_validate_scope(scope))
    counts=_skill_counts(jobs)
    top=[{"skill":skill,"jobs":count} for skill,count in sorted(counts.items(),key=lambda item:(-item[1],item[0]))[:limit]]
    return {"top":top,"trend":_weekly_skill_trend(jobs,[item["skill"] for item in top[:5]],weeks)}

@app.get("/analytics/companies")
def company_patterns(limit:int=Query(15,ge=1,le=100),weeks:int=Query(12,ge=1,le=104),scope:Literal["all","india","remote","india_remote"]="all",user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    jobs=_analytics_jobs(db,_validate_scope(scope))
    companies={}
    by_type=Counter()
    by_source=Counter()
    weekly=Counter()
    for job in jobs:
        name=job.company.company_name
        item=companies.setdefault(name,{"company":name,"jobs":0,"internships":0,"last_seen":job.scraped_at})
        item["jobs"]+=1
        item["internships"]+=int((job.job_type or "").casefold()=="internship")
        item["last_seen"]=max(item["last_seen"],job.scraped_at)
        by_type[job.job_type or "unknown"]+=1
        by_source[job.source or "manual"]+=1
        posted=job.posted_date or job.scraped_at.date()
        if posted>=date.today()-timedelta(weeks=weeks):
            week=posted-timedelta(days=posted.weekday())
            weekly[week]+=1
    remote=sum(job.is_remote for job in jobs)
    india=sum(job.is_india is True for job in jobs)
    top=sorted(companies.values(),key=lambda item:(-item["jobs"],item["company"].casefold()))[:limit]
    return {
        "totals":{"active_jobs":len(jobs),"remote":remote,"india":india,"companies":len(companies)},
        "top_companies":top,
        "by_type":[{"type":key,"jobs":value} for key,value in by_type.most_common()],
        "by_source":[{"source":key,"jobs":value} for key,value in by_source.most_common()],
        "weekly":[{"week":week.isoformat(),"jobs":count} for week,count in sorted(weekly.items())],
    }

@app.get("/analytics/skill-gap",dependencies=[Depends(require_admin)])
def skill_gap(limit:int=Query(25,ge=1,le=100),weeks:int=Query(12,ge=1,le=104),scope:Literal["all","india","remote","india_remote"]="all",db:Session=Depends(get_db)):
    jobs=_analytics_jobs(db,_validate_scope(scope))
    students=db.scalars(select(Students).where(Students.role=="student")).all()
    demand=_skill_counts([job for job in jobs if job.necessary_skills])
    supply=Counter()
    for student in students:
        supply.update({skill.strip().casefold() for skill in (student.skills or []) if skill.strip()})
    total_jobs=sum(bool(job.necessary_skills) for job in jobs)
    rows=[]
    for skill,count in sorted(demand.items(),key=lambda item:(-item[1],item[0]))[:limit]:
        demand_pct=round(100*count/total_jobs,1) if total_jobs else 0.0
        supply_pct=round(100*supply[skill]/len(students),1) if students else 0.0
        rows.append({"skill":skill,"jobs":count,"students":supply[skill],"demand_pct":demand_pct,"supply_pct":supply_pct,"gap_pct":round(demand_pct-supply_pct,1)})
    rows.sort(key=lambda item:(-item["gap_pct"],item["skill"]))
    top_skills=[item["skill"] for item in rows[:5]]
    return {
        "total_students":len(students),
        "total_jobs_with_skills":total_jobs,
        "skills":rows,
        "trend":_weekly_skill_trend(jobs,top_skills,weeks),
    }

@app.get("/analytics/curriculum",dependencies=[Depends(require_admin)])
def curriculum_alignment(scope:Literal["all","india","remote","india_remote"]="all",db:Session=Depends(get_db)):
    try:
        data=yaml.safe_load(Path(__file__).with_name("curriculum.yaml").read_text(encoding="utf-8"))
        courses=data.get("courses") if isinstance(data,dict) else None
        if not isinstance(courses,list) or not courses:
            raise ValueError("curriculum.yaml needs a non-empty courses list")
    except (OSError,yaml.YAMLError,ValueError) as exc:
        logger.exception("Could not load curriculum.yaml")
        raise HTTPException(status_code=500,detail=f"curriculum.yaml: {exc}") from exc
    jobs=_analytics_jobs(db,_validate_scope(scope))
    demand=_skill_counts(jobs)
    total_jobs=sum(bool(job.necessary_skills) for job in jobs)
    taught=set()
    result=[]
    for course in courses:
        if not isinstance(course,dict) or not isinstance(course.get("name"),str) or not isinstance(course.get("skills"),list):
            raise HTTPException(status_code=500,detail="curriculum.yaml has an invalid course")
        skills=sorted({str(value).strip().casefold() for value in course["skills"] if str(value).strip()})
        taught.update(skills)
        matching=sum(bool({skill.strip().casefold() for skill in (job.necessary_skills or [])}&set(skills)) for job in jobs)
        result.append({
            "course":course["name"],
            "jobs_mentioning":matching,
            "jobs_pct":round(100*matching/total_jobs,1) if total_jobs else 0.0,
            "skills":[{"skill":skill,"jobs":demand.get(skill,0)} for skill in skills],
        })
    mentions=sum(demand.values())
    covered=sum(count for skill,count in demand.items() if skill in taught)
    return {
        "total_jobs_with_skills":total_jobs,
        "alignment_pct":round(100*covered/mentions,1) if mentions else 0.0,
        "courses":sorted(result,key=lambda item:-item["jobs_mentioning"]),
        "uncovered_skills":[{"skill":skill,"jobs":count} for skill,count in demand.items() if skill not in taught][:15],
    }

@app.get("/metrics",include_in_schema=False)
def metrics():
    return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)

@app.post("/internal/alerts/run",dependencies=[Depends(ingest_auth)])
@app.post("/internal/trigger_alerts",status_code=202,dependencies=[Depends(ingest_auth)])
def job_alert_trigger(bg:BackgroundTasks):
    bg.add_task(job_alerts)
    return {'status':'started'}

@app.get("/me/stats",response_model=MyStats)
def student_stats(limit:int=Query(10, ge=1, le=50),user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    MATCH_FLOOR=40
    matches=[(j, s) for j,s in compute_matches(user,db) if s is not None and s>=MATCH_FLOOR]   
    scores_id={j.id:s for j,s in matches}    
    mine={s.strip().lower() for s in user.skills}
    wanted={}
    for job,_ in matches:
        for s in job.necessary_skills:
            s=s.lower().strip()
            if s and s not in mine:
                wanted[s]=wanted.get(s,0)+1
    gap=sorted(wanted.items(),key=lambda x:(-x[1],x[0]))[:limit]     
    early=get_early_jobs(db, job_ids=list(scores_id),limit=10)  
    return {
        "matching_jobs":len(matches),
        "apply_early":[
            {"id": j.id, "title": j.title,"company_name":j.company.company_name,
             "apply_url":j.apply_url,"score":scores_id[j.id]}
            for j in early
        ],
        "top_skills":topskills(db, limit),
        "skill_gap":[{"skill": k, "jobs": v} for k,v in gap]
    }
    
@app.get("/me/resume")
def download_resume(user: Students = Depends(get_current_user)):
    if not user.resume_file:
        raise HTTPException(status_code=404,detail="No resume uploaded")
    path=RESUME_PATH/user.resume_file
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Resume file missing")
    return FileResponse(path,media_type="application/pdf",filename="resume.pdf")

@app.post("/me/resume")
def upload_and_parse(file:UploadFile=File(...),user=Depends(get_current_user),db:Session=Depends(get_db)):
    data=file.file.read(10_000_001)
    if len(data)>10_000_000:
        raise HTTPException(status_code=413,detail="File too large. Max 10 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=415,detail="Only PDF Files allowed")
    try:
        resume_data=pdf_to_text(data)
    except Exception:
        raise HTTPException(status_code=422, detail="Could not read this PDF")
    if len(resume_data.strip()) < 50:
        raise HTTPException(status_code=422, detail="No text found (scanned PDF?)")
    name=f"{user.id}_{secrets.token_hex(8)}.pdf"   
    (RESUME_PATH/name).write_bytes(data)
    old=user.resume_file
    user.resume_file=name
    try:
        db.commit()
    except Exception:
        db.rollback()
        (RESUME_PATH/name).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Could not save resume")
    if old:
        (RESUME_PATH / old).unlink(missing_ok=True)

    found=extract_skills(resume_data,load_vocab(db))
    mine={s.lower() for s in user.skills}
    return {
        "has_resume": True,
        "skills": found,
        "new_skills": [s for s in found if s not in mine],
        "cgpa": extract_cgpa(resume_data),
        "grad_year": extract_grad_year(resume_data),
    }
