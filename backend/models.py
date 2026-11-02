from datetime import datetime,date
from sqlalchemy import String, Text, Integer, Float, Boolean, Date, DateTime,ForeignKey, UniqueConstraint, CheckConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db import Base

class Students(Base):
    __tablename__="students"

    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(100),nullable=False)
    branch:Mapped[str|None]=mapped_column(String(100),nullable=True)
    email:Mapped[str]=mapped_column(String(255),unique=True,nullable=False,index=True)
    password_hash:Mapped[str]=mapped_column(String(255),nullable=False,index=True)
    grad_year:Mapped[int]=mapped_column(Integer,nullable=False)
    role:Mapped[str]=mapped_column(String(100),default='student')
    cgpa:Mapped[float|None]=mapped_column(Float)
    skills:Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    resume_file:Mapped[str|None]=mapped_column(String(100))
    @property
    def has_resume(self) -> bool:
        return self.resume_file is not None
    resume_link:Mapped[str|None]=mapped_column(Text)
    alerts_enabled:Mapped[bool]=mapped_column(Boolean, default=True,server_default="true")
    embedding:Mapped[list[float] | None]=mapped_column(ARRAY(Float))
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    matches:Mapped[list["Match"]]=relationship(back_populates='student')
    applications:Mapped[list["Application"]]=relationship(back_populates="student",cascade="all,delete-orphan")

class Companies(Base):
    __tablename__="company"

    id:Mapped[int]=mapped_column(primary_key=True)
    company_name:Mapped[str]=mapped_column(String(100),nullable=False,unique=True)
    careers_url:Mapped[str]=mapped_column(String(1024),nullable=False)
    description:Mapped[str|None]=mapped_column(Text)
    jobs:Mapped[list["Job"]]=relationship(back_populates="company")

class Job(Base):
    __tablename__="job_postings"
    __table_args__=(UniqueConstraint("source","external_id",name="uq_job_source_external_id"),)

    id:Mapped[int]=mapped_column(primary_key=True)
    company_id:Mapped[int]=mapped_column(ForeignKey("company.id"),index=True)
    title:Mapped[str]=mapped_column(String(255),nullable=False)
    description: Mapped[str|None]=mapped_column(Text)
    location:Mapped[str|None]=mapped_column(String(150))
    job_type:Mapped[str|None]=mapped_column(String(30)) 
    min_cgpa:Mapped[float|None]=mapped_column(Float)
    allowed_branches:Mapped[list[str]]=mapped_column(ARRAY(String),default=list,nullable=True)
    allowed_grads:Mapped[list[int]]=mapped_column(ARRAY(Integer),default=list)
    necessary_skills:Mapped[list[str]]=mapped_column(ARRAY(String), default=list)
    apply_url:Mapped[str | None]=mapped_column(String(500))
    content_hash:Mapped[str]=mapped_column(String(64), unique=True)
    is_active:Mapped[bool]=mapped_column(Boolean, default=True)
    embedding:Mapped[list[float]|None]=mapped_column(ARRAY(Float))
    source:Mapped[str|None]=mapped_column(String(50),index=True)
    external_id:Mapped[str|None]=mapped_column(String(255))
    source_content_hash:Mapped[str|None]=mapped_column(String(64))
    is_remote:Mapped[bool]=mapped_column(Boolean,default=False,server_default=text("false"))
    is_india:Mapped[bool|None]=mapped_column(Boolean)
    work_mode:Mapped[str|None]=mapped_column(String(20))
    posted_date:Mapped[date|None]=mapped_column(Date)
    scraped_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    deadline_at:Mapped[date|None]=mapped_column(Date,index=True)
    company:Mapped["Companies"]=relationship(back_populates='jobs')
    matches:Mapped[list["Match"]]=relationship(back_populates='job')
    last_seen_at:Mapped[date]=mapped_column(DateTime,server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    applications:Mapped[list["Application"]]=relationship(back_populates="job",cascade="all,delete-orphan")

    @property
    def company_name(self)->str:
        return self.company.company_name

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

class Application(Base):
    __tablename__="applications"
    __table_args__=(
        UniqueConstraint("student_id","job_id",name="uq_application_student_job"),
        CheckConstraint(
            "status IN ('saved','applied','assessment','interview','offer','rejected','withdrawn')",
            name="ck_application_status",
        ),
    )

    id:Mapped[int]=mapped_column(primary_key=True)
    student_id:Mapped[int]=mapped_column(ForeignKey("students.id",ondelete="CASCADE"),index=True)
    job_id:Mapped[int]=mapped_column(ForeignKey("job_postings.id",ondelete="CASCADE"),index=True)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default="applied",server_default="applied")
    notes:Mapped[str|None]=mapped_column(Text)
    applied_at:Mapped[datetime|None]=mapped_column(DateTime)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    updated_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    student:Mapped["Students"]=relationship(back_populates="applications")
    job:Mapped["Job"]=relationship(back_populates="applications")

class ScrapedRuns(Base):
    __tablename__="scrapes"

    id:Mapped[int]=mapped_column(primary_key=True)
    started_at: Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    scrap_status:Mapped[str]=mapped_column(String(20),default="running")
    jobs_found:Mapped[int]=mapped_column(Integer,default=0)
