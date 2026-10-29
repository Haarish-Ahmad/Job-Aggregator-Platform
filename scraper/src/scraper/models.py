from datetime import date, datetime
from enum import Enum
from typing import Literal

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


class JobExtraction(BaseModel):
    """Fields only an LLM can read out of free text. Every value is optional: null means 'not stated'."""

    skills: list[str] = Field(default_factory=list, description="Technologies/skills explicitly named in the posting")
    degree_required: Literal["bachelors", "masters", "phd", "none"] | None = Field(
        default=None, description="Minimum degree the posting asks for; 'none' if it says no degree is needed"
    )
    graduation_years: list[int] = Field(
        default_factory=list, description="Graduation/batch years the posting targets, e.g. [2026, 2027]"
    )
    work_mode: WorkMode | None = None
    salary_min: float | None = Field(
        default=None, description="Lowest pay figure exactly as written in the posting (no arithmetic)"
    )
    salary_max: float | None = None
    salary_unit: Literal["thousand", "lakh", "crore", "million"] | None = Field(
        default=None,
        exclude=True,  # only a scratch field: code multiplies it out, so stored salaries are plain numbers
        description="Unit word written next to the figures, if any",
    )
    salary_currency: str | None = Field(default=None, description="ISO code such as INR, USD")
    salary_period: Literal["hour", "month", "year"] | None = None
    work_authorization_restricted: bool | None = Field(
        default=None,
        description="True only if the posting says applicants must be citizens/residents of, or authorized to work in, a specific country",
    )
    work_authorization_note: str | None = Field(
        default=None, description="The exact sentence from the posting that says so"
    )


class ExtractionResult(BaseModel):
    model: str
    prompt_version: str
    extracted_at: datetime
    data: JobExtraction


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
    description_text: str = ""  # full cleaned text; the LLM stage reads this

    # LLM-derived; kept apart from everything above so it can never overwrite source data.
    extraction: ExtractionResult | None = None


class FailedJob(BaseModel):
    source: str
    external_id: str
    url: str
    stage: str
    error: str
    at: datetime
