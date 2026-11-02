from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class EmploymentType(str, Enum):
    internship = "internship"
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    unknown = "unknown"


class WorkMode(str, Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"


class SearchFilters(BaseModel):
    queries: list[str]
    locations: list[str]
    limit: int


class JobRef(BaseModel):
    """What discovery returns: enough to identify a job and fetch its detail."""

    external_id: str
    url: str
    # Extra info the search results already gave us (title, location...), so adapters
    # don't have to ask twice.
    hints: dict = Field(default_factory=dict)


class RawJob(BaseModel):
    """What an adapter returns for one job, before any cleaning/normalizing."""

    ref: JobRef
    content: str  # markdown or plain text of the posting
    fields: dict = Field(default_factory=dict)  # structured data the source gave us directly


class JobRecord(BaseModel):
    # Set by code, never guessed.
    source: str
    company: str
    external_id: str
    url: str
    scraped_at: datetime
    content_hash: str

    title: str
    requisition_id: str | None = None
    employment_type: EmploymentType = EmploymentType.unknown
    employment_type_raw: str | None = None
    work_mode: WorkMode | None = None
    locations: list[str] = Field(default_factory=list)
    department: str | None = None
    posted_date: date | None = None
    min_experience_years: int | None = None

    overview: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    required_qualifications: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)
    description_text: str = ""  # full cleaned text; skills are read from it (see skills.py)


class FailedJob(BaseModel):
    source: str
    external_id: str
    url: str
    stage: str
    error: str
    at: datetime
