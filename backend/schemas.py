from pydantic import BaseModel,ConfigDict,EmailStr,Field,field_validator
from datetime import date

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
    password:str
    branch:str|None=None
    cgpa:float|None=None
    grad_year:int
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
    model_config=ConfigDict(from_attributes=True)

class ingestionResult(BaseModel):
    inserted:int
    skipped:int

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
    grad_year:int|None=None
    skills:list[str]|None=None 
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
    model_config = ConfigDict(from_attributes=True)    

class MatchOut(BaseModel):
    score:float
    job:JobOut