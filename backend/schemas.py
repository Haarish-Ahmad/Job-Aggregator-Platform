from typing import Literal
from pydantic import BaseModel,ConfigDict,EmailStr,Field,field_validator
from datetime import date, datetime

class CompanyDetails(BaseModel):
    company_name:str
    careers_url:str
    description:str|None=None

class CompanyOut(CompanyDetails):
    id:int
    model_config=ConfigDict(from_attributes=True)

class StudentDetails(BaseModel):
    name:str
    email:EmailStr
    password:str=Field(min_length=8,max_length=128)
    branch:str|None=None
    cgpa:float|None=Field(default=None,ge=0,le=10)
    grad_year:int=Field(ge=2000,le=2100)
    skills:list[str]=[]
    resume_link:str|None=None

class LoginDetails(BaseModel):
    email:EmailStr
    password:str

class StudentOut(BaseModel):
    id:int
    name:str
    email:EmailStr
    branch:str|None
    cgpa:float|None
    grad_year:int|None
    skills:list[str]
    role:str
    resume_link:str|None
    alerts_enabled:bool=False
    model_config=ConfigDict(from_attributes=True)

# Column sizes, mirrored from models.py. Ingest checks them per record so one bad record is
# rejected with a reason instead of failing the whole batch with a database error.
FIELD_LIMITS={"company_name":100,"title":255,"location":150,"job_type":30,"apply_url":500,
              "source":50,"external_id":255,"source_content_hash":64,"work_mode":20}
MAX_INGEST_BATCH=500

Status=Literal["inserted","updated","unchanged","rejected"]

class RecordResult(BaseModel):
    index:int
    status:Status
    job_id:int|None=None
    reason:str|None=None

class ingestionResult(BaseModel):
    inserted:int
    skipped:int
    # Additive fields: older clients that only read inserted/skipped keep working.
    updated:int=0
    rejected:int=0
    results:list[RecordResult]=[]

class jobsIn(BaseModel):
    company_name:str
    title:str
    apply_url:str
    location:str | None = None
    job_type:str | None = None
    description:str | None = None
    min_cgpa:float | None = None
    allowed_branches:list[str] = []
    allowed_grads:list[int] = []
    required_skills:list[str] = []
    deadline:date | None = None
    # Optional, sent by the scraper. source + external_id together identify a posting.
    source:str | None = None
    external_id:str | None = None
    source_content_hash:str | None = None
    is_remote:bool = False
    is_india:bool | None = None
    work_mode:str | None = None
    posted_date:date | None = None

    @field_validator("allowed_branches","required_skills")
    @classmethod
    def check_skills(cls,v):
        if not v:
            return v
        return [s.strip().lower() for s in v]

class bulkjobs(BaseModel):
    jobs:list[jobsIn]=Field(max_length=MAX_INGEST_BATCH)

class StudentUpdate(BaseModel):
    branch:str|None=None
    cgpa:float|None=Field(default=None, ge=0, le=10)
    grad_year:int|None=Field(default=None,ge=2000,le=2100)
    skills:list[str]|None=None 
    resume_link:str|None=None
    alerts_enabled:bool|None=None
    @field_validator("skills")
    @classmethod
    def clean_skills(cls,val):
        if not val:
            return val
        return [s.strip().lower() for s in val]

class JobOut(BaseModel):
    id: int
    company_id: int
    title: str
    description: str | None = None
    location: str | None = None
    job_type: str | None = None
    min_cgpa: float | None = None
    allowed_branches: list[str] = []
    allowed_grads: list[int] = []
    necessary_skills: list[str] = []
    apply_url: str | None = None
    deadline_at: date | None = None
    is_active: bool
    company_name: str | None = None
    source: str | None = None
    external_id: str | None = None
    is_remote: bool = False
    is_india: bool | None = None
    work_mode: str | None = None
    posted_date: date | None = None
    scraped_at: datetime | None = None
    last_seen_at: datetime | None = None
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)    

class MatchOut(BaseModel):
    score:float
    job:JobOut
# Application tracker. Mirrors models.APPLICATION_STATUSES.
ApplicationStatus=Literal["saved","applied","interview","offer","rejected"]

class ApplicationCreate(BaseModel):
    # Only the job: a new application is always 'saved'. Any other field sent (e.g. a status) is ignored.
    job_id:int

class ApplicationUpdate(BaseModel):
    status:ApplicationStatus|None=None
    applied_on:date|None=None

class ApplicationOut(BaseModel):
    id:int
    status:ApplicationStatus
    saved_on:date
    applied_on:date|None
    updated_at:datetime|None=None
    job:JobOut
    model_config=ConfigDict(from_attributes=True)
