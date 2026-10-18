from fastapi import FastAPI,Depends,HTTPException,Request
from sqlalchemy.orm import Session
from sqlalchemy import select
from db import get_db
from starlette.middleware.sessions import SessionMiddleware
from models import Companies,Students,Job
from werkzeug.security import generate_password_hash,check_password_hash
from schemas import CompanyDetails, CompanyOut, StudentDetails, StudentOut, LoginDetails, StudentUpdate, jobsIn, JobOut, ingestionResult, bulkjobs, MatchOut
from fastapi.middleware.cors import CORSMiddleware
import hashlib
from matching import compute_matches, save_matches
import os

app=FastAPI(title="Job Aggregator Platform")
app.add_middleware(SessionMiddleware,secret_key=os.getenv("SECRET_KEY","dev-secret-change-me"),
    max_age=60 * 60 * 12,same_site="lax",https_only=False)

app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173"],allow_credentials=True,
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

def make_hash(company: str, title: str, location: str | None) -> str:
    raw = f"{company}|{title}|{location or ''}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()

@app.get("/health")
def check_health():
    return {'status':'ok'}

@app.post("/company",response_model=CompanyOut,status_code=201)
def company_create(data:CompanyDetails,db:Session=Depends(get_db)):
    if db.scalars(select(Companies).where(Companies.company_name==data.company_name)).first():
        raise HTTPException(status_code=409,detail="Company already exist")
    c=Companies(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

@app.get("/companies",response_model=list[CompanyOut])
def list_company(db:Session=Depends(get_db)):
    return db.scalars(select(Companies)).all()

@app.post("/auth/register",response_model=StudentOut,status_code=201)
def student_register(data:StudentDetails,db:Session=Depends(get_db)):
    if db.scalars(select(Students).where(data.email==Students.email)).first():
        raise HTTPException(status_code=409,detail="Student Exists")
    password_hash=generate_password_hash(data.password)
    student=Students(**data.model_dump(exclude={"password"}),password_hash=password_hash)
    db.add(student)
    db.commit()
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
    for field,val in data.model_dump(exclude_unset=True).items():
        setattr(user,field,val)
    db.commit()
    db.refresh(user)
    return user    

@app.post("/internal/jobs",response_model=ingestionResult)
def get_jobs(data:bulkjobs,user:Students=Depends(get_current_user),db:Session=Depends(get_db)):
    if user.role!="admin":
        raise HTTPException(status_code=403,detail="Method not allowed")
    inserted=skipped=0
    for item in data.jobs:
        company=db.scalars(select(Companies).where(item.company_name==Companies.company_name)).first() 
        if not company:
            company=Companies(company_name=item.company_name,careers_url=item.apply_url,description=item.description)
            db.add(company)
            db.flush()
        h=make_hash(item.company_name,item.title,item.location)
        if db.scalars(select(Job).where(Job.content_hash==h)).first():
            skipped+=1
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
            deadline_at=item.deadline))  
        inserted+=1
    db.commit()
    return ingestionResult(inserted=inserted,skipped=skipped)

@app.get("/jobs",response_model=list[JobOut])  
def jobs(q: str | None = None,company_id: int | None = None,job_type: str | None = None,active_only: bool = True,limit: int = 50,offset: int = 0,user: Students = Depends(get_current_user),db: Session = Depends(get_db)):
    query=select(Job)
    if q:
        query=query.where(Job.title.ilike(f"%{q}%"))
    if company_id:
        query=query.where(Job.company_id==company_id)
    if job_type:
        query=query.where(Job.job_type==job_type)
    if active_only:
        query=query.where(Job.is_active.is_(True))   
    query=query.order_by(Job.scraped_at.desc()).limit(min(limit, 100)).offset(offset)  
    return db.scalars(query).all()  

@app.get("/jobs/{job_id}",response_model=JobOut)
def get_job_with_id(job_id:int,db:Session=Depends(get_db)):
    job=db.get(Job,job_id)
    if not job:
        raise HTTPException(status_code=404,detail="job not found")
    return job

@app.get("/me/matches",response_model=list[MatchOut])
def get_matches(user:Students=Depends(get_current_user),min_score:float=0,db:Session=Depends(get_db)):
    result=compute_matches(user,db)
    save_matches(user,result,db)
    db.commit()
    return [{"score":s,"job":j} for j,s in result if s>=min_score]

