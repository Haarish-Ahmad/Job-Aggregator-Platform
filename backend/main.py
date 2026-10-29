from typing import Any,Callable,Literal
from fastapi import FastAPI,Depends,HTTPException,Query,Request,Response
from sqlalchemy.orm import Session,contains_eager
from sqlalchemy import any_,literal,select,func,or_,text
from db import get_db
from starlette.middleware.sessions import SessionMiddleware
from models import Companies,Students,Job
from werkzeug.security import generate_password_hash,check_password_hash
from schemas import CompanyDetails, CompanyOut, StudentDetails, StudentOut, LoginDetails, StudentUpdate, JobOut, ingestionResult, bulkjobs, MatchOut
from fastapi.middleware.cors import CORSMiddleware
from matching import compute_matches, save_matches
from config import get_settings
from deps import get_current_user,ingest_auth
from ingest import deactivate_stale,ingest,make_hash  # noqa: F401  (make_hash re-exported: it used to live here)
from metrics import MetricsMiddleware,metrics_response,INGEST_RECORDS
import alerts
import analytics

settings=get_settings()
app=FastAPI(title="Job Aggregator Platform",root_path=settings.root_path)
app.add_middleware(SessionMiddleware,secret_key=settings.secret_key,
    max_age=60 * 60 * 12,same_site="lax",https_only=settings.session_cookie_secure)

app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origin_list,allow_credentials=True,
    allow_methods=["*"],allow_headers=["*"],expose_headers=["X-Total-Count"])
app.add_middleware(MetricsMiddleware)

app.include_router(alerts.router)
app.include_router(analytics.router)

@app.get("/health")
def check_health(db:Session=Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503,detail="database unavailable") from None
    return {'status':'ok','db':'ok'}

@app.get("/metrics",include_in_schema=False)
def metrics():
    return metrics_response()

@app.post("/company",response_model=CompanyOut,status_code=201)
def company_create(data:CompanyDetails,user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    if db.scalars(select(Companies).where(Companies.company_name==data.company_name)).first():
        raise HTTPException(status_code=409,detail="Company already exist")
    c=Companies(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

@app.get("/companies",response_model=list[CompanyOut])
def list_company(user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    return db.scalars(select(Companies)).all()

@app.post("/auth/register",response_model=StudentOut,status_code=201)
def student_register(data:StudentDetails,db:Session=Depends(get_db)):
    if db.scalars(select(Students).where(Students.email==data.email)).first():
        raise HTTPException(status_code=409,detail="Student Exists")
    password_hash=generate_password_hash(data.password)
    student=Students(**data.model_dump(exclude={"password"}),password_hash=password_hash)
    db.add(student)
    db.commit()
    db.refresh(student)
    return student

@app.post("/auth/login",response_model=StudentOut)
def login(data: LoginDetails,request: Request,db:Session=Depends(get_db)):
    user=db.scalars(select(Students).where(Students.email==data.email)).first()
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
    for field,val in data.model_dump(exclude_unset=True).items():
        setattr(user,field,val)
    db.commit()
    db.refresh(user)
    return user

@app.post("/internal/jobs",response_model=ingestionResult)
def get_jobs(data:bulkjobs,auth=Depends(ingest_auth),db:Session=Depends(get_db)):
    result=ingest(db,data.jobs)
    for status,n in (("inserted",result.inserted),("updated",result.updated),("unchanged",result.skipped),("rejected",result.rejected)):
        INGEST_RECORDS.labels(status).inc(n)
    return result

@app.post("/internal/maintenance/deactivate-stale")
def stale_postings(days:int|None=Query(default=None,ge=1,le=3650),auth=Depends(ingest_auth),db:Session=Depends(get_db)):
    """Retire scraped postings the scraper has not seen for `days` (default STALE_DAYS)."""
    return {"deactivated":deactivate_stale(db,days or settings.stale_days)}

def _like(value:str)->str:
    """Escape LIKE wildcards so a search for '%' or '_' matches literally."""
    return "%"+value.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"

SORTS:dict[str,Callable[[],tuple[Any,...]]]={
    "newest":lambda: (Job.scraped_at.desc(),Job.id.desc()),
    "oldest":lambda: (Job.scraped_at.asc(),Job.id.asc()),
    "deadline":lambda: (Job.deadline_at.asc().nulls_last(),Job.id.desc()),
    "title":lambda: (func.lower(Job.title).asc(),Job.id.asc()),
}

@app.get("/jobs",response_model=list[JobOut])
def jobs(response:Response,q: str | None = None,company_id: int | None = None,job_type: str | None = None,active_only: bool = True,
    limit: int = Query(50,ge=1),offset: int = Query(0,ge=0),
    location: str | None = None,skill: str | None = None,grad_year: int | None = None,source: str | None = None,
    scope: Literal["all","india","remote","india_remote"] = "all",hide_expired: bool = False,
    sort: Literal["newest","oldest","deadline","title"] = "newest",
    user: Students = Depends(get_current_user),db: Session = Depends(get_db)):
    query=select(Job).join(Job.company).options(contains_eager(Job.company))
    if q:
        query=query.where(or_(Job.title.ilike(_like(q),escape="\\"),Companies.company_name.ilike(_like(q),escape="\\")))
    if company_id:
        query=query.where(Job.company_id==company_id)
    if job_type:
        query=query.where(Job.job_type==job_type)
    if active_only:
        query=query.where(Job.is_active.is_(True))
    if hide_expired:
        query=query.where(or_(Job.deadline_at.is_(None),Job.deadline_at>=func.current_date()))
    if location:
        query=query.where(Job.location.ilike(_like(location),escape="\\"))
    if skill:
        query=query.where(literal(skill.strip().lower())==any_(Job.necessary_skills))
    if grad_year:
        query=query.where(or_(func.coalesce(func.cardinality(Job.allowed_grads),0)==0,literal(grad_year)==any_(Job.allowed_grads)))
    if source:
        query=query.where(Job.source==source)
    if scope=="india":
        query=query.where(Job.is_india.is_(True))
    elif scope=="remote":
        query=query.where(Job.is_remote.is_(True))
    elif scope=="india_remote":
        query=query.where(or_(Job.is_india.is_(True),Job.is_remote.is_(True)))
    response.headers["X-Total-Count"]=str(db.scalar(select(func.count()).select_from(query.order_by(None).subquery())))
    query=query.order_by(*SORTS[sort]()).limit(min(limit, 100)).offset(offset)
    return db.scalars(query).unique().all()

@app.get("/jobs/{job_id}",response_model=JobOut)
def get_job_with_id(job_id:int,user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job:
        raise HTTPException(status_code=404,detail="job not found")
    return job

@app.get("/me/matches",response_model=list[MatchOut])
def get_matches(user:Students=Depends(get_current_user),min_score:float=0,include_unmatched:bool=False,db:Session=Depends(get_db)):
    result=compute_matches(user,db)
    save_matches(user,result,db)
    db.commit()
    # A job that shares none of the student's skills (0%) is not a match, unless asked for.
    return [{"score":s,"job":j} for j,s in result if s>=min_score and (include_unmatched or s>0)]
