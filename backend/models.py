"""Pydantic request/response models (validation lives here)."""
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


class ApplicationStatus(str, Enum):
    SAVED = "Saved"
    APPLIED = "Applied"
    ASSESSMENT = "Assessment"
    INTERVIEW = "Interview"
    OFFER = "Offer"
    REJECTED = "Rejected"
    WITHDRAWN = "Withdrawn"


# Applications in these statuses are still "open", so follow-ups make sense.
# Offer / Rejected / Withdrawn are treated as closed.
ACTIVE_STATUSES = {"Saved", "Applied", "Assessment", "Interview"}

_REQUIRED_TEXT = {"company_name", "job_title"}


# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------
class _CleanedModel(BaseModel):
    """Shared text clean-up: trims whitespace, turns '' into None, checks the URL."""

    @field_validator(
        "company_name", "job_title", "job_description", "job_url",
        "notes", "resume_version", "location",
        mode="before", check_fields=False,
    )
    @classmethod
    def _strip_text(cls, value: Any, info: ValidationInfo) -> Any:
        if isinstance(value, str):
            value = value.strip() or None
        if value is None and info.field_name in _REQUIRED_TEXT:
            label = "Company name" if info.field_name == "company_name" else "Job title"
            raise ValueError(f"{label} is required and cannot be empty.")
        return value

    @field_validator("job_url", check_fields=False)
    @classmethod
    def _check_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Job URL must start with http:// or https://")
        return value


class ApplicationBase(_CleanedModel):
    company_name: str = Field(..., max_length=200)
    job_title: str = Field(..., max_length=200)
    job_description: Optional[str] = Field(default=None, max_length=20000)
    job_url: Optional[str] = Field(default=None, max_length=2000)
    application_date: Optional[date] = None
    status: ApplicationStatus = ApplicationStatus.SAVED
    follow_up_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=5000)
    resume_version: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)
    # Free-form output of the AI extraction (skills, experience, ...).
    extracted_info: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _check_dates(self) -> "ApplicationBase":
        if self.application_date and self.follow_up_date and self.follow_up_date < self.application_date:
            raise ValueError("Follow-up date cannot be before the application date.")
        return self


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(_CleanedModel):
    """Partial update: only the fields that are sent are changed.
    Send an explicit null to clear an optional field."""

    company_name: Optional[str] = Field(default=None, max_length=200)
    job_title: Optional[str] = Field(default=None, max_length=200)
    job_description: Optional[str] = Field(default=None, max_length=20000)
    job_url: Optional[str] = Field(default=None, max_length=2000)
    application_date: Optional[date] = None
    status: Optional[ApplicationStatus] = None
    follow_up_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=5000)
    resume_version: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)
    extracted_info: Optional[Dict[str, Any]] = None

    @field_validator("status", mode="before")
    @classmethod
    def _status_not_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Status cannot be empty.")
        return value


class ApplicationOut(BaseModel):
    """What the API returns. Deliberately lenient so old rows never break a response."""

    id: str
    company_name: str
    job_title: str
    job_description: Optional[str] = None
    job_url: Optional[str] = None
    application_date: Optional[date] = None
    status: str
    follow_up_date: Optional[date] = None
    notes: Optional[str] = None
    resume_version: Optional[str] = None
    location: Optional[str] = None
    extracted_info: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HistoryOut(BaseModel):
    id: str
    application_id: str
    old_status: Optional[str] = None
    new_status: str
    note: Optional[str] = None
    changed_at: datetime
    company_name: Optional[str] = None
    job_title: Optional[str] = None


# --------------------------------------------------------------------------
# Dashboard, follow-ups, analytics
# --------------------------------------------------------------------------
class DashboardStats(BaseModel):
    total_applications: int
    interviews: int
    offers: int
    rejections: int
    follow_ups_due: int  # open applications with a follow-up date today or earlier
    status_counts: Dict[str, int]


class FollowUpItem(ApplicationOut):
    days_until: int  # negative = overdue


class FollowUpsOut(BaseModel):
    overdue: List[FollowUpItem]
    today: List[FollowUpItem]
    upcoming: List[FollowUpItem]


class MonthlyCount(BaseModel):
    month: str  # "2026-10"
    count: int


class ResumeStat(BaseModel):
    resume_version: str
    applications: int
    interviews_or_offers: int


class AnalyticsOut(BaseModel):
    total_applications: int
    status_counts: Dict[str, int]
    monthly_applications: List[MonthlyCount]
    response_rate: float   # % of submitted applications that moved past "Applied"
    interview_rate: float  # % of submitted applications at Interview or Offer
    offer_rate: float      # % of submitted applications at Offer
    resume_performance: List[ResumeStat]


# --------------------------------------------------------------------------
# AI endpoints
# --------------------------------------------------------------------------
def _strip_or_none(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip() or None
    return value


class ExtractJobRequest(BaseModel):
    job_description: str = Field(..., min_length=30, max_length=20000)

    @field_validator("job_description", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class ExtractedJob(BaseModel):
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None          # Remote / Hybrid / On-site
    employment_type: Optional[str] = None    # Full-time / Internship / ...
    experience_required: Optional[str] = None
    salary_range: Optional[str] = None
    skills: List[str] = []
    responsibilities: List[str] = []
    qualifications: List[str] = []
    summary: Optional[str] = None

    @field_validator("skills", "responsibilities", "qualifications", mode="before")
    @classmethod
    def _clean_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(v).strip() for v in value if str(v).strip()][:30]

    @field_validator(
        "company_name", "job_title", "location", "work_mode", "employment_type",
        "experience_required", "salary_range", "summary", mode="before",
    )
    @classmethod
    def _clean_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return _strip_or_none(str(value))


class ExtractJobResponse(BaseModel):
    extracted: ExtractedJob
    source: str  # "gemini" or "demo"


class FollowUpEmailRequest(BaseModel):
    application_id: str
    tone: Literal["professional", "friendly", "concise"] = "professional"
    sender_name: Optional[str] = Field(default=None, max_length=100)
    extra_context: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("sender_name", "extra_context", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return _strip_or_none(value)


class FollowUpEmailResponse(BaseModel):
    subject: str
    body: str
    source: str


class InterviewQuestionsRequest(BaseModel):
    # Either an existing application, or a pasted job description.
    application_id: Optional[str] = None
    job_title: Optional[str] = Field(default=None, max_length=200)
    job_description: Optional[str] = Field(default=None, max_length=20000)
    count: int = Field(default=10, ge=3, le=20)

    @field_validator("application_id", "job_title", "job_description", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return _strip_or_none(value)

    @model_validator(mode="after")
    def _need_source(self) -> "InterviewQuestionsRequest":
        if not self.application_id and not (self.job_description and len(self.job_description) >= 30):
            raise ValueError("Provide an application_id, or a job_description of at least 30 characters.")
        return self


class InterviewQuestion(BaseModel):
    category: str
    question: str
    tip: Optional[str] = None
    answer: Optional[str] = None


class InterviewQuestionsResponse(BaseModel):
    job_title: Optional[str] = None
    questions: List[InterviewQuestion]
    source: str


class DemoSeedResponse(BaseModel):
    inserted: int
