from pydantic import BaseModel,ConfigDict,EmailStr,Field,field_validator
from datetime import date,datetime
from typing import Literal
import re

SPECIAL_CHARS=r"""!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~"""

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
    password:str=Field(min_length=8,max_length=100)
    branch:str|None=Field(default=None, max_length=100)
    cgpa:float|None=Field(default=None, ge=0, le=10)
    grad_year:int=Field(ge=2000, le=2040)
    skills:list[str]=[]
    resume_link:str|None=None
    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        errors=[]
        if not re.search(r"[A-Z]", v):
            errors.append("one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("one lowercase letter")
        if not re.search(r"\d", v):
            errors.append("one digit")
        if not re.search(rf"[{SPECIAL_CHARS}]", v):
            errors.append("one special character")
        if re.search(r"\s", v):
            errors.append("no spaces")
        if errors:
            raise ValueError("Password needs: " + ", ".join(errors))
        return v

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
    alerts_enabled:bool=True
    model_config=ConfigDict(from_attributes=True)

class RecordResult(BaseModel):
    index:int
    status:Literal["inserted","updated","unchanged","rejected"]
    job_id:int|None=None
    reason:str|None=None

class ingestionResult(BaseModel):
    inserted:int
    skipped:int
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
    source:str | None = None
    external_id:str | None = None
    source_content_hash:str | None = None
    is_remote:bool=False
    is_india:bool|None=None
    work_mode:str|None=None
    posted_date:date|None=None

    @field_validator("allowed_branches","required_skills")
    @classmethod
    def check_skills(cls,v):
        if not v:
            return v
        return [s.strip().lower() for s in v]

class bulkjobs(BaseModel):
    jobs:list[jobsIn]   

class StudentUpdate(BaseModel):
    branch:str|None=None
    cgpa:float|None=Field(default=None, ge=0, le=10)
    grad_year:int|None=Field(default=None, ge=2020, le=2040)
    skills:list[str]|None=None 
    alerts_enabled: bool|None=None
    resume_link:str|None=None
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
    company_name:str|None=None
    source:str|None=None
    external_id:str|None=None
    is_remote:bool=False
    is_india:bool|None=None
    work_mode:str|None=None
    posted_date:date|None=None
    scraped_at:datetime|None=None
    last_seen_at:datetime|None=None
    updated_at:datetime|None=None
    model_config = ConfigDict(from_attributes=True)    

class MatchOut(BaseModel):
    score:float
    job:JobOut

class SkillCount(BaseModel):
    skill: str
    jobs: int    

class Analytics(BaseModel):
    companies:int
    active_jobs:list[JobOut]
    active_jobs_count:int
    jobs_this_week:list[JobOut]
    average_match:float
    topskill:list[SkillCount]
    students:int
    early_jobs:list[JobOut]
    late_jobs:list[JobOut]
    top_posting:list[str]

class EarlyJob(BaseModel):
    id:int
    title:str
    company_name:str
    apply_url:str | None=None
    score:float

class MyStats(BaseModel):
    matching_jobs:int
    apply_early: list[EarlyJob]
    top_skills: list[SkillCount]
    skill_gap: list[SkillCount]