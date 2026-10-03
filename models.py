from datetime import datetime,date
from sqlalchemy import String, Text, Integer, Float, Boolean, Date, DateTime,ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db import Base

class Students(Base):
    __tablename__="students"

    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(100),nullable=False)
    branch:Mapped[str]=mapped_column(String(100))
    email:Mapped[str]=mapped_column(String(255),unique=True,nullable=False,index=True)
    password_hash:Mapped[str]=mapped_column(String(255),unique=True,nullable=False,index=True)
    year_grad:Mapped[int]=mapped_column(nullable=False)
    role:Mapped[str]=mapped_column(String(100),default='student')
    cgpa:Mapped[float|None]=mapped_column(Float)
    grad_year:Mapped[int | None] = mapped_column(Integer)
    skills:Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    resume_link:Mapped[str|None]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    matches:Mapped[list["Match"]]=relationship(back_populates='student')

class Companies(Base):
    __tablename__="company"

    id:Mapped[int]=mapped_column(primary_key=True)
    company_name:Mapped[str]=mapped_column(String(100),nullable=False,unique=True)
    careers_url:Mapped[str]=mapped_column(String(255),nullable=False)
    description:Mapped[str|None]=mapped_column(Text)
    jobs:Mapped[list["Job"]]=relationship(back_populates="company")

class Job(Base):
    __tablename__="job_postings"

    id:Mapped[int]=mapped_column(primary_key=True)
    company_id:Mapped[int]=mapped_column(ForeignKey("company.id"),index=True)
    title:Mapped[str]=mapped_column(String(255),nullable=False)
    description: Mapped[str|None]=mapped_column(Text)
    location:Mapped[str|None]=mapped_column(String(150))
    job_type:Mapped[str|None]=mapped_column(String(30)) 
    min_cgpa:Mapped[float|None]=mapped_column(Float)
    allowed_branches:Mapped[list[str]]=mapped_column(ARRAY(String),default=list,nullable=True)
    allowed_grads:Mapped[list[int]]=mapped_column(ARRAY(Integer),default=list)
    year_grad:Mapped[int]=mapped_column(nullable=False)
    necessary_skills:Mapped[list[str]]=mapped_column(ARRAY(String), default=list)
    apply_url:Mapped[str | None]=mapped_column(String(500))
    content_hash:Mapped[str]=mapped_column(String(64), unique=True)
    is_active:Mapped[bool]=mapped_column(Boolean, default=True)
    scraped_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    deadline_at:Mapped[date|None]=mapped_column(Date,index=True)
    company:Mapped["Companies"]=relationship(back_populates='jobs')
    matches:Mapped[list["Match"]]=relationship(back_populates='job')

class Match(Base):
    __tablename__="matches"
    __table_args__=(UniqueConstraint("student_id", "job_id", name="uq_student_job"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey("students.id"),index=True)
    job_id:Mapped[int]=mapped_column(ForeignKey("job_postings.id"),index=True)
    score:Mapped[float]=mapped_column(Float)
    notified_at:Mapped[datetime|None]=mapped_column(DateTime) 
    student:Mapped["Students"]=relationship(back_populates="matches")
    job:Mapped["Job"]=relationship(back_populates="matches")

class ScrapedRuns(Base):
    __tablename__="scrapes"
    id:Mapped[int]=mapped_column(primary_key=True)
    started_at: Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    scrap_status:Mapped[str]=mapped_column(String(20),default="running")
    jobs_found:Mapped[int]=mapped_column(Integer,default=0)
