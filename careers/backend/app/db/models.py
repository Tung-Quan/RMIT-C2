from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    tide_identity_key = Column(String(64), unique=True, index=True, nullable=True)
    full_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=True)
    role = Column(String(20), default="candidate", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    applications = relationship(
        "CandidateApplication",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    candidate_profile = relationship(
        "CandidateProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    owned_company = relationship(
        "Company",
        back_populates="owner",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="Company.owner_user_id",
    )
    created_job_postings = relationship(
        "JobPosting",
        back_populates="created_by_user",
        foreign_keys="JobPosting.created_by_user_id",
    )
    job_applications = relationship(
        "JobApplication",
        back_populates="candidate_user",
        foreign_keys="JobApplication.candidate_user_id",
    )
    status_changes = relationship(
        "ApplicationStatusHistory",
        back_populates="changed_by_user",
        foreign_keys="ApplicationStatusHistory.changed_by_user_id",
    )


class GatewayAssertion(Base):
    __tablename__ = "gateway_assertions"
    id = Column(String(36), primary_key=True)
    expires_at = Column(BigInteger, nullable=False, index=True)


class CandidateApplication(Base):
    __tablename__ = "candidate_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_name = Column(String(255), nullable=False)
    position_title = Column(String(255), nullable=False)
    job_description = Column(Text, nullable=False)
    application_status = Column(String(50), default="Saved", nullable=False)
    deadline = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="applications")
    documents = relationship(
        "Document",
        back_populates="application",
        cascade="all, delete-orphan",
    )
    ai_results = relationship(
        "AIAnalysisResult",
        back_populates="application",
        cascade="all, delete-orphan",
    )
    interview_questions = relationship(
        "InterviewQuestion",
        back_populates="application",
        cascade="all, delete-orphan",
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id = Column(
        Integer,
        ForeignKey("candidate_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_url = Column(Text, nullable=False)
    s3_key = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="documents")
    application = relationship("CandidateApplication", back_populates="documents")
    extracted_text = relationship(
        "DocumentText",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    job_application_links = relationship(
        "JobApplicationDocument",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    full_name = Column(String(255), nullable=True)
    university = Column(String(255), nullable=True)
    major = Column(String(255), nullable=True)
    graduation_year = Column(Integer, nullable=True)
    phone = Column(String(50), nullable=True)
    location = Column(String(255), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    github_url = Column(String(500), nullable=True)
    portfolio_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="candidate_profile")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    website = Column(String(500), nullable=True)
    industry = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner = relationship("User", back_populates="owned_company", foreign_keys=[owner_user_id])
    job_postings = relationship(
        "JobPosting", back_populates="company", cascade="all, delete-orphan"
    )


class JobPosting(Base):
    __tablename__ = "job_postings"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    requirements = Column(Text, nullable=True)
    responsibilities = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    employment_type = Column(String(50), default="early_career", nullable=False)
    work_mode = Column(String(50), default="onsite", nullable=False)
    salary_min = Column(BigInteger, nullable=True)
    salary_max = Column(BigInteger, nullable=True)
    deadline = Column(Date, nullable=True)
    status = Column(String(50), default="draft", nullable=False)
    version = Column(Integer, default=1, server_default="1", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # AI parser fields
    ai_parse_status = Column(String(50), default="not_started", nullable=False)
    ai_parsed_profile = Column(JSON, nullable=True)
    ai_parse_error = Column(Text, nullable=True)
    ai_parsed_at = Column(DateTime(timezone=True), nullable=True)
    ai_parse_revision = Column(Integer, default=0, nullable=False)

    company = relationship("Company", back_populates="job_postings")
    created_by_user = relationship(
        "User", back_populates="created_job_postings", foreign_keys=[created_by_user_id]
    )
    applications = relationship(
        "JobApplication", back_populates="job_posting", cascade="all, delete-orphan"
    )


class JobApplication(Base):
    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint(
            "job_posting_id",
            "candidate_user_id",
            name="uq_job_applications_job_candidate",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    job_posting_id = Column(
        Integer,
        ForeignKey("job_postings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = Column(String(50), default="submitted", nullable=False)
    cover_letter_text = Column(Text, nullable=True)
    candidate_note = Column(Text, nullable=True)
    version = Column(Integer, default=1, server_default="1", nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # AI parser fields
    ai_cv_parse_status = Column(String(50), default="not_started", nullable=False)
    ai_cv_parsed_profile = Column(JSON, nullable=True)
    ai_cv_parse_error = Column(Text, nullable=True)
    ai_cv_parsed_at = Column(DateTime(timezone=True), nullable=True)
    ai_cv_parse_revision = Column(Integer, default=0, nullable=False)

    job_posting = relationship("JobPosting", back_populates="applications")
    candidate_user = relationship(
        "User", back_populates="job_applications", foreign_keys=[candidate_user_id]
    )
    attached_documents = relationship(
        "JobApplicationDocument",
        back_populates="job_application",
        cascade="all, delete-orphan",
    )
    status_history = relationship(
        "ApplicationStatusHistory",
        back_populates="job_application",
        cascade="all, delete-orphan",
        order_by="ApplicationStatusHistory.created_at.asc()",
    )


class JobApplicationDocument(Base):
    __tablename__ = "job_application_documents"
    __table_args__ = (
        UniqueConstraint(
            "job_application_id",
            "document_id",
            name="uq_job_application_documents_attachment",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    job_application_id = Column(
        Integer,
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job_application = relationship("JobApplication", back_populates="attached_documents")
    document = relationship("Document", back_populates="job_application_links")


class ApplicationStatusHistory(Base):
    __tablename__ = "application_status_history"

    id = Column(Integer, primary_key=True, index=True)
    job_application_id = Column(
        Integer,
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)
    changed_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job_application = relationship("JobApplication", back_populates="status_history")
    changed_by_user = relationship(
        "User", back_populates="status_changes", foreign_keys=[changed_by_user_id]
    )


class DocumentText(Base):
    __tablename__ = "document_texts"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    raw_text = Column(Text, nullable=True)
    blocks_json = Column(JSON, nullable=True)
    semantic_groups_json = Column(JSON, nullable=True)
    parser_name = Column(String(100), nullable=False)
    parser_version = Column(String(100), nullable=False)
    text_hash = Column(String(128), nullable=True, index=True)
    extraction_status = Column(String(50), default="pending", nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    document = relationship("Document", back_populates="extracted_text")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="ck_idempotency_records_status",
        ),
        UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_records_scope_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    scope = Column(String(255), nullable=False, index=True)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="processing")
    response_status = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'DEAD')",
            name="ck_outbox_events_status",
        ),
        UniqueConstraint("deduplication_key", name="uq_outbox_events_deduplication_key"),
        Index("ix_outbox_events_claimable", "status", "available_at"),
        Index("ix_outbox_events_processing_lease", "status", "locked_until"),
        Index(
            "ix_outbox_events_aggregate",
            "aggregate_type",
            "aggregate_id",
            "aggregate_version",
        ),
        Index("ix_outbox_events_published_cleanup", "status", "published_at"),
        Index("ix_outbox_events_dead", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    event_type = Column(String(100), nullable=False)
    schema_version = Column(Integer, nullable=False)
    aggregate_type = Column(String(50), nullable=False)
    aggregate_id = Column(String(100), nullable=False)
    aggregate_version = Column(Integer, nullable=False)
    command_name = Column(String(50), nullable=False)
    causation_id = Column(String(36), nullable=False)
    correlation_id = Column(String(36), nullable=True)
    deduplication_key = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    available_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String(100), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AsyncProcessingJob(Base):
    __tablename__ = "async_processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_async_processing_jobs_status",
        ),
        UniqueConstraint(
            "deduplication_key",
            name="uq_async_processing_jobs_deduplication_key",
        ),
        Index("ix_async_processing_jobs_claimable", "status", "available_at"),
        Index("ix_async_processing_jobs_running_lease", "status", "locked_until"),
        Index("ix_async_processing_jobs_owner_status", "owner_user_id", "status"),
        Index("ix_async_processing_jobs_type_status", "job_type", "status"),
        Index(
            "ix_async_processing_jobs_related_entity", "related_entity_type", "related_entity_id"
        ),
        Index(
            "ix_async_processing_jobs_source_entity",
            "source_entity_type",
            "source_entity_id",
            "source_version",
        ),
    )

    id = Column(String(36), primary_key=True)
    job_type = Column(String(80), nullable=False)
    status = Column(String(32), nullable=False, default="queued", server_default="queued")
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requester_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    related_entity_type = Column(String(80), nullable=True)
    related_entity_id = Column(String(80), nullable=True)
    source_entity_type = Column(String(80), nullable=True)
    source_entity_id = Column(String(80), nullable=True)
    source_version = Column(Integer, nullable=True)
    source_checksum = Column(String(128), nullable=True)
    deduplication_key = Column(String(255), nullable=False)
    input_json = Column(JSON, nullable=False)
    result_json = Column(JSON, nullable=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    max_attempts = Column(Integer, nullable=False, default=3, server_default="3")
    available_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String(100), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(80), nullable=True)
    last_error_message = Column(String(512), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner_user = relationship("User", foreign_keys=[owner_user_id])
    requester_user = relationship("User", foreign_keys=[requester_user_id])


class AIAnalysisResult(Base):
    __tablename__ = "ai_analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(
        Integer,
        ForeignKey("candidate_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cv_text = Column(Text, nullable=False)
    job_description = Column(Text, nullable=False)
    match_score = Column(Integer, nullable=False)
    matched_skills = Column(JSON, default=list, nullable=False)
    missing_skills = Column(JSON, default=list, nullable=False)
    suggested_improvements = Column(JSON, default=list, nullable=False)
    cover_letter = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    application = relationship("CandidateApplication", back_populates="ai_results")


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(
        Integer,
        ForeignKey("candidate_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question = Column(Text, nullable=False)
    answer_hint = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    application = relationship("CandidateApplication", back_populates="interview_questions")


class JobRerankRun(Base):
    __tablename__ = "job_rerank_runs"

    id = Column(Integer, primary_key=True, index=True)
    job_posting_id = Column(
        Integer, ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), default="pending", nullable=False)  # pending, completed, failed
    model_name = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    job_posting = relationship("JobPosting", backref="rerank_runs")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    application_results = relationship(
        "ApplicationRerankResult", back_populates="rerank_run", cascade="all, delete-orphan"
    )


class ApplicationRerankResult(Base):
    __tablename__ = "application_rerank_results"
    __table_args__ = (
        UniqueConstraint("rerank_run_id", "job_application_id", name="uq_app_rerank_result"),
    )

    id = Column(Integer, primary_key=True, index=True)
    rerank_run_id = Column(
        Integer, ForeignKey("job_rerank_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_application_id = Column(
        Integer, ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )

    criterion_results_json = Column(JSON, nullable=False)
    global_relevance_score = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    rerank_run = relationship("JobRerankRun", back_populates="application_results")
    job_application = relationship("JobApplication", backref="rerank_results")
