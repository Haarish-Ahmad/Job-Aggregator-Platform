from fastapi import FastAPI,Depends,HTTPException,Request,Header,Response,Query,BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select,func,update,text
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from metrics import MetricsMiddleware
from db import get_db,engine
from starlette.middleware.sessions import SessionMiddleware
from models import Companies,Students,Job
from werkzeug.security import generate_password_hash,check_password_hash
from schemas import CompanyDetails, Analytics, CompanyOut, StudentDetails, StudentOut, LoginDetails, StudentUpdate, JobOut, MyStats, ingestionResult, bulkjobs, MatchOut, RecordResult
from fastapi.middleware.cors import CORSMiddleware
import hashlib
from analytics import general_stats,deactivate_expired,get_dontapply_jobs,get_early_jobs,top_postings,topskills,skills_report,skill_gap_report,companies_report,curriculum_report
import secrets
from target_companies import offcampus_targets
from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from datetime import timedelta,date
from config import INGEST_TOKEN,ALERT_LOCK_ID,SECRET_KEY,RESUME_DIR,COOKIE_SECURE,CORS_ORIGINS
from matching import compute_matches, save_matches, embed,job_text, student_text
from alert import run_alerts
from pathlib import Path
import os
from resume import pdf_to_text,load_vocab,extract_cgpa,extract_grad_year,extract_skills

RESUME_PATH=Path(RESUME_DIR)
RESUME_PATH.mkdir(exist_ok=True)

app=FastAPI(title="Job Aggregator Platform",root_path=os.getenv("ROOT_PATH",""))
app.add_middleware(SessionMiddleware,secret_key=SECRET_KEY,
    max_age=60*60*12,same_site="lax",https_only=COOKIE_SECURE)
app.add_middleware(MetricsMiddleware)
app.add_middleware(CORSMiddleware,allow_origins=CORS_ORIGINS,allow_credentials=True,
    allow_methods=["*"],allow_headers=["*"])

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

def ingest_auth(ingest_token:str|None=Header(default=None)):
    if not INGEST_TOKEN:
        raise HTTPException(status_code=403,detail="Ingestion not found")
    if not ingest_token or not secrets.compare_digest(ingest_token,INGEST_TOKEN):
        raise HTTPException(status_code=401,detail="Invalid ingest token")

def make_hash(company: str, title: str, location: str | None) -> str:
    raw = f"{company}|{title}|{location or ''}".lower().strip()
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
def check_health():
    return {'status':'ok'}

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
    company_ids=set()
    for index,item in enumerate(data.jobs):
        company=db.scalars(select(Companies).where(item.company_name.lower()==func.lower(Companies.company_name))).first()
        if not company:
            company=Companies(company_name=item.company_name,careers_url=item.apply_url,description=None)
            db.add(company)
            db.flush()
        company_ids.add(company.id)
        h=hashlib.sha256(f"{item.source}|{item.external_id}".encode()).hexdigest() if item.source and item.external_id else make_hash(item.company_name,item.title,item.location)
        existing=None
        if item.source and item.external_id:
            existing=db.scalars(select(Job).where(Job.source==item.source,Job.external_id==item.external_id)).first()
        if not existing:
            existing=db.scalars(select(Job).where(Job.content_hash==h)).first()
        source_hash=item.source_content_hash or hashlib.sha256(
            f"{item.title}|{item.description}|{item.required_skills}|{item.apply_url}|{item.location}".encode()
        ).hexdigest()
        if existing:
            embedding_changed=(
                existing.title!=item.title
                or existing.description!=item.description
                or existing.necessary_skills!=item.required_skills
            )
            content_changed=(
                existing.source_content_hash!=source_hash
                or existing.company_id!=company.id
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
                or existing.is_remote!=item.is_remote
                or existing.is_india!=item.is_india
                or existing.work_mode!=item.work_mode
                or existing.posted_date!=item.posted_date
            )
            existing.content_hash=h
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
            existing.source_content_hash=source_hash
            existing.is_remote=item.is_remote
            existing.is_india=item.is_india
            existing.work_mode=item.work_mode
            existing.posted_date=item.posted_date
            if embedding_changed:
                existing.embedding=embed([job_text(item.title,item.required_skills,item.description)])[0]
            existing.last_seen_at=func.now()
            existing.is_active=not (existing.deadline_at and existing.deadline_at<date.today())
            if content_changed:
                existing.updated_at=func.now()
                existing.scraped_at=func.now()
                updated+=1
                results.append(RecordResult(index=index,status="updated",job_id=existing.id))
            else:
                skipped+=1
                results.append(RecordResult(index=index,status="unchanged",job_id=existing.id))
            continue   
        db.add(Job(company_id=company.id,
            title=item.title,
            description=item.description,
            location=item.location,
            job_type=item.job_type,
            min_cgpa=item.min_cgpa,
            allowed_branches=item.allowed_branches,
            allowed_grads=item.allowed_grads,
            necessary_skills=item.required_skills,
            apply_url=item.apply_url,
            content_hash=h,
            embedding=embed([job_text(item.title,item.required_skills,item.description)])[0],
            deadline_at=item.deadline,
            source=item.source,
            external_id=item.external_id,
            source_content_hash=source_hash,
            is_remote=item.is_remote,
            is_india=item.is_india,
            work_mode=item.work_mode,
            posted_date=item.posted_date))
        inserted+=1
        results.append(RecordResult(index=index,status="inserted"))
    if company_ids:
        stale_days=int(os.getenv("STALE_DAYS","14"))
        db.execute(update(Job).where(
            Job.company_id.in_(company_ids),
            Job.is_active.is_(True),
            Job.last_seen_at<func.now()-timedelta(days=stale_days),
            Job.source.is_(None)
        ).values(is_active=False))
    deactivate_expired(db)
    db.commit()
    return ingestionResult(inserted=inserted,updated=updated,skipped=skipped,rejected=rejected,results=results)

@app.get("/jobs",response_model=list[JobOut])
def jobs(response:Response,q:str|None=None,search:str|None=None,company_id:int|None=None,job_type:str|None=None,active_only:bool=True,hide_expired:bool|None=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),location:str|None=None,company:str|None=None,source:str|None=None,scope:str|None=None,skill:str|None=None,grad_year:int|None=None,sort:str="newest",user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    query=select(Job)
    search_term=search or q
    if search_term:
        query=query.where(Job.title.ilike(f"%{search_term}%")|Job.description.ilike(f"%{search_term}%"))
    if company_id:
        query=query.where(Job.company_id==company_id)
    if job_type:
        query=query.where(func.lower(Job.job_type)==job_type.lower())
    if hide_expired is True or (hide_expired is None and active_only):
        query=query.where(Job.is_active.is_(True))
    if location:
        query=query.where(Job.location.ilike(f"%{location}%"))
    if source:
        query=query.where(Job.source==source)
    if skill:
        query=query.where(Job.necessary_skills.any(skill.lower()))
    if grad_year:
        query=query.where((Job.allowed_grads==[])|Job.allowed_grads.contains([grad_year]))
    if company:
        query=query.join(Companies,Job.company_id==Companies.id).where(Companies.company_name.ilike(f"%{company}%"))
    if scope=="india":
        query=query.where(Job.is_india.is_(True))
    elif scope=="remote":
        query=query.where(Job.is_remote.is_(True))
    elif scope=="india_remote":
        query=query.where(Job.is_india.is_(True)|Job.is_remote.is_(True))
    elif scope not in (None,"all"):
        raise HTTPException(status_code=400,detail="Invalid scope")
    total=db.scalar(select(func.count()).select_from(query.subquery())) or 0
    response.headers["X-Total-Count"]=str(total)
    sort_columns={"newest":Job.scraped_at.desc(),"oldest":Job.scraped_at.asc(),"deadline":Job.deadline_at.asc().nullslast(),"title":Job.title.asc()}
    if sort not in sort_columns:
        raise HTTPException(status_code=400,detail="Invalid sort")
    query=query.order_by(sort_columns[sort]).limit(limit).offset(offset)
    return db.scalars(query).all()

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

@app.get("/analytics/skills",dependencies=[Depends(require_admin)])
def analytics_skills(scope:str="all",limit:int=Query(20,ge=1,le=100),weeks:int=Query(12,ge=1,le=52),db:Session=Depends(get_db)):
    try:
        return skills_report(db,scope,limit,weeks)
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc

@app.get("/analytics/skill-gap",dependencies=[Depends(require_admin)])
def analytics_skill_gap(scope:str="all",limit:int=Query(20,ge=1,le=100),weeks:int=Query(12,ge=1,le=52),db:Session=Depends(get_db)):
    try:
        return skill_gap_report(db,scope,limit,weeks)
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc

@app.get("/analytics/companies",dependencies=[Depends(require_admin)])
def analytics_companies(scope:str="all",limit:int=Query(20,ge=1,le=100),weeks:int=Query(12,ge=1,le=52),db:Session=Depends(get_db)):
    try:
        return companies_report(db,scope,limit,weeks)
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc

@app.get("/analytics/curriculum",dependencies=[Depends(require_admin)])
def analytics_curriculum(scope:str="all",limit:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    try:
        return curriculum_report(db,scope,limit)
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc

@app.get("/metrics",include_in_schema=False,dependencies=[Depends(require_admin)])
def metrics():
    return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)

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
