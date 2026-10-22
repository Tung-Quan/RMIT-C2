from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.password_validation import validate_password_complexity

APPLICATION_STATUS_VALUES = [
    "Saved",
    "Applied",
    "Interview",
    "Offer",
    "Rejected",
    "Accepted",
]
DOCUMENT_TYPE_VALUES = ["CV", "Transcript", "Certificate", "Other"]
USER_ROLE_VALUES = ["candidate", "hr", "admin"]
JOB_POSTING_STATUS_VALUES = ["draft", "published", "closed"]
JOB_EMPLOYMENT_TYPE_VALUES = ["early_career", "part_time", "full_time"]
JOB_WORK_MODE_VALUES = ["onsite", "hybrid", "remote"]
MAX_SAFE_SALARY_VALUE = 9_007_199_254_740_991
JOB_APPLICATION_STATUS_VALUES = [
    "submitted",
    "under_review",
    "shortlisted",
    "interview",
    "offered",
    "rejected",
    "withdrawn",
]

ApplicationStatus = Literal["Saved", "Applied", "Interview", "Offer", "Rejected", "Accepted"]
DocumentType = Literal["CV", "Transcript", "Certificate", "Other"]
UserRole = Literal["candidate", "hr", "admin"]
JobPostingStatus = Literal["draft", "published", "closed"]
JobEmploymentType = Literal["early_career", "part_time", "full_time"]
JobWorkMode = Literal["onsite", "hybrid", "remote"]
JobApplicationStatus = Literal[
    "submitted",
    "under_review",
    "shortlisted",
    "interview",
    "offered",
    "rejected",
    "withdrawn",
]
ApplicationAdvanceTarget = Literal["under_review", "shortlisted", "interview", "offered"]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = "candidate"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_complexity(v)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr | None
    full_name: str | None
    role: UserRole
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ApplicationBase(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    position_title: str = Field(min_length=1, max_length=255)
    job_description: str = Field(min_length=1)
    application_status: ApplicationStatus = "Saved"
    deadline: date | None = None
    notes: str | None = None


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    position_title: str | None = Field(default=None, min_length=1, max_length=255)
    job_description: str | None = Field(default=None, min_length=1)
    application_status: ApplicationStatus | None = None
    deadline: date | None = None
    notes: str | None = None


class ApplicationRead(ApplicationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    application_id: int
    document_type: DocumentType
    file_name: str
    created_at: datetime


class DocumentDownloadUrl(BaseModel):
    document_id: int
    download_url: str
    expires_in: int


class DocumentTextStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    parser_name: str
    parser_version: str
    text_hash: str | None
    extraction_status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentTextResponse(DocumentTextStatusResponse):
    raw_text: str | None
    blocks_json: list[dict] | None
    semantic_groups_json: list[dict] | None


class DocumentTextExtractResponse(DocumentTextResponse):
    skipped_cached: bool = False


class BulkApplicantTextExtractionResponse(BaseModel):
    job_id: int
    total_documents: int
    succeeded: int
    failed: int
    unsupported: int
    skipped_cached: int
    results: list[DocumentTextExtractResponse]


class ProcessingJobRead(BaseModel):
    id: str
    job_type: str
    status: str
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    source_entity_type: str | None = None
    source_entity_id: str | None = None
    source_version: int | None = None
    attempts: int
    max_attempts: int
    available_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    result: dict | None = None
    created_at: datetime
    updated_at: datetime
    version: int


class BulkApplicantTextExtractionEnqueueResponse(BaseModel):
    job_id: int
    total_documents: int
    queued: int
    skipped_cached: int
    results: list[ProcessingJobRead | DocumentTextExtractResponse]


class CandidateProfileBase(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    university: str | None = Field(default=None, max_length=255)
    major: str | None = Field(default=None, max_length=255)
    graduation_year: int | None = Field(default=None, ge=1900, le=2100)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    bio: str | None = None


class CandidateProfileUpdate(CandidateProfileBase):
    pass


class CandidateProfileRead(CandidateProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class CompanyBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    logo_url: str | None = Field(default=None, max_length=500)


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    logo_url: str | None = Field(default=None, max_length=500)


class CompanySummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    industry: str | None
    location: str | None
    website: str | None
    logo_url: str | None


class CompanyRead(CompanySummaryRead):
    description: str | None
    owner_user_id: int
    created_at: datetime
    updated_at: datetime


class JobPostingBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    requirements: str | None = None
    responsibilities: str | None = None
    location: str | None = Field(default=None, max_length=255)
    employment_type: JobEmploymentType = "early_career"
    work_mode: JobWorkMode = "onsite"
    salary_min: int | None = Field(default=None, ge=0, le=MAX_SAFE_SALARY_VALUE)
    salary_max: int | None = Field(default=None, ge=0, le=MAX_SAFE_SALARY_VALUE)
    deadline: date | None = None

    @model_validator(mode="after")
    def validate_salary_range(self):
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("salary_max must be greater than or equal to salary_min")
        return self


class JobPostingCreate(JobPostingBase):
    status: JobPostingStatus = "draft"


class JobPostingUpdate(BaseModel):
    expectedVersion: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    requirements: str | None = None
    responsibilities: str | None = None
    location: str | None = Field(default=None, max_length=255)
    employment_type: JobEmploymentType | None = None
    work_mode: JobWorkMode | None = None
    salary_min: int | None = Field(default=None, ge=0, le=MAX_SAFE_SALARY_VALUE)
    salary_max: int | None = Field(default=None, ge=0, le=MAX_SAFE_SALARY_VALUE)
    deadline: date | None = None
    status: JobPostingStatus | None = None

    @model_validator(mode="after")
    def validate_salary_range(self):
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("salary_max must be greater than or equal to salary_min")
        return self


class JobPostingStatusUpdate(BaseModel):
    expectedVersion: int = Field(ge=1)
    status: JobPostingStatus


class WorkflowCommandRequest(BaseModel):
    expectedVersion: int = Field(ge=1)


class JobCommandRequest(WorkflowCommandRequest):
    pass


class JobDeleteResult(BaseModel):
    id: int
    status: Literal["deleted"]
    version: int
    message: str


class JobPostingRead(JobPostingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    created_by_user_id: int
    status: JobPostingStatus
    version: int
    created_at: datetime
    updated_at: datetime
    company: CompanySummaryRead

    ai_parse_status: str
    ai_parsed_profile: dict | None = None
    ai_parse_error: str | None = None
    ai_parsed_at: datetime | None = None
    ai_parse_revision: int


class JobPostingProcessingResponse(BaseModel):
    job: JobPostingRead
    processing_job: ProcessingJobRead


class AttachedDocumentRead(BaseModel):
    id: int
    document_id: int
    document_type: DocumentType
    file_name: str
    created_at: datetime


class StatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    old_status: str | None
    new_status: str
    changed_by_user_id: int | None
    note: str | None
    created_at: datetime


class JobPostingSummaryRead(BaseModel):
    id: int
    title: str
    location: str | None
    work_mode: JobWorkMode
    employment_type: JobEmploymentType
    deadline: date | None
    status: JobPostingStatus
    version: int
    company: CompanySummaryRead


class JobApplicationCreate(BaseModel):
    cover_letter_text: str | None = None
    candidate_note: str | None = None
    document_ids: list[int] = Field(min_length=1)


class JobApplicationSummaryRead(BaseModel):
    id: int
    job_posting_id: int
    status: JobApplicationStatus
    version: int
    submitted_at: datetime
    updated_at: datetime
    job_posting: JobPostingSummaryRead
    attached_documents_count: int


class CandidateSummaryRead(BaseModel):
    id: int
    email: EmailStr | None
    full_name: str | None
    profile: CandidateProfileRead | None = None


class JobApplicationDetailRead(BaseModel):
    id: int
    job_posting_id: int
    candidate_user_id: int
    status: JobApplicationStatus
    version: int
    cover_letter_text: str | None
    candidate_note: str | None
    submitted_at: datetime
    updated_at: datetime
    job_posting: JobPostingRead
    attached_documents: list[AttachedDocumentRead]
    status_history: list[StatusHistoryRead]


class HRJobApplicationDetailRead(JobApplicationDetailRead):
    candidate: CandidateSummaryRead

    ai_cv_parse_status: str
    ai_cv_parsed_profile: dict | None = None
    ai_cv_parse_error: str | None = None
    ai_cv_parsed_at: datetime | None = None
    ai_cv_parse_revision: int


class HRJobApplicationProcessingResponse(BaseModel):
    application: HRJobApplicationDetailRead
    processing_job: ProcessingJobRead


class HRApplicantSummaryRead(BaseModel):
    id: int
    candidate_user_id: int
    candidate_name: str
    candidate_email: EmailStr | None
    status: JobApplicationStatus
    version: int
    submitted_at: datetime
    attached_documents_count: int


class StatusUpdateRequest(BaseModel):
    expectedVersion: int = Field(ge=1)
    status: JobApplicationStatus
    note: str | None = None


class CandidateWithdrawRequest(BaseModel):
    expectedVersion: int = Field(ge=1)


class ApplicationAdvanceRequest(WorkflowCommandRequest):
    targetStage: ApplicationAdvanceTarget
    note: str | None = None


class ApplicationRejectRequest(WorkflowCommandRequest):
    reason: str | None = Field(default=None, max_length=2000)


class CandidateDeadlineRead(BaseModel):
    type: Literal["tracker", "job"]
    label: str
    deadline: date
    status: str


class CandidateDashboardRead(BaseModel):
    total_personal_applications: int
    total_submitted_job_applications: int
    recent_documents: list[DocumentRead]
    upcoming_deadlines: list[CandidateDeadlineRead]
    recent_job_applications: list[JobApplicationSummaryRead]


class HRDashboardRead(BaseModel):
    company: CompanyRead | None
    total_jobs: int
    published_jobs: int
    total_applicants: int
    recent_applications: list[HRApplicantSummaryRead]


class AIAnalyzeRequest(BaseModel):
    cv_text: str | None = Field(default=None, min_length=1)
    document_id: int | None = None

    @model_validator(mode="after")
    def require_cv_text_or_document(self):
        if not self.cv_text and not self.document_id:
            raise ValueError("Provide cv_text or a .txt CV document_id.")
        return self


class AIAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    cv_text: str
    job_description: str
    match_score: int
    matched_skills: list[str]
    missing_skills: list[str]
    suggested_improvements: list[str]
    cover_letter: str
    created_at: datetime


class InterviewQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    question: str
    answer_hint: str
    created_at: datetime


class DashboardStats(BaseModel):
    total_applications: int
    applications_by_status: dict[str, int]
    uploaded_documents: int
    average_ai_match_score: float
    recent_applications: list[ApplicationRead]


class CriterionResultRead(BaseModel):
    criterion_index: int
    criterion_name: str
    criterion_source_text: str | None = None
    importance: str
    status: str
    explanation: str
    evidence_text: str | None = None
    evidence_name: str | None = None
    internal_evidence_score: float | None = None


class ApplicationRerankResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_application_id: int
    criterion_results_json: list[CriterionResultRead] | dict | list[dict]
    global_relevance_score: int | None
    created_at: datetime


class JobRerankRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_posting_id: int
    created_by_user_id: int | None
    status: str
    model_name: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    application_results: list[ApplicationRerankResultRead] = Field(default_factory=list)


class JobRerankRunProcessingResponse(BaseModel):
    rerank_run: JobRerankRunRead
    processing_job: ProcessingJobRead
