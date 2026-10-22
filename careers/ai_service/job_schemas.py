from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ai_service.job_cleaning import (
    clean_text_block,
    clean_to_list,
    description_duplicates_title,
)


class EmploymentType(str, Enum):
    """
    Loại hình tuyển dụng được website hỗ trợ.

    Field này chỉ dùng để hiển thị và quản lý job.
    Nó không được sử dụng để đánh giá CV.
    """

    EARLY_CAREER = "early_career"
    PART_TIME = "part_time"
    FULL_TIME = "full_time"


class WorkMode(str, Enum):
    """
    Hình thức làm việc.

    Field này không tham gia CV ranking.
    """

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class JobStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


def clean_single_line(value: str) -> str:
    """
    Chuẩn hóa field một dòng như job title và location.

    Ví dụ:
        "  Backend   Developer Intern  "
    trở thành:
        "Backend Developer Intern"
    """

    return " ".join(value.split())


def clean_multiline(value: str) -> str:
    """
    Chuẩn hóa newline nhưng giữ nguyên nội dung và bullet point.

    Các dạng sau vẫn được giữ:
        - Python
        • PostgreSQL
        1. Communication
        + Docker
    """

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")

    # Chỉ xóa khoảng trắng thừa ở cuối từng dòng.
    normalized = "\n".join(
        line.rstrip()
        for line in normalized.split("\n")
    )

    return normalized.strip()


class JobEvaluationInput(BaseModel):
    """
    Phần dữ liệu thực sự được gửi tới Qwen3-4B để tạo criteria.

    Không chứa:
    - salary
    - work mode
    - employment type
    - deadline
    - status
    - location

    Những field trên không phải bằng chứng năng lực trong CV.

    .. deprecated::
        Preserved for backward compatibility.  New code should use
        :class:`JobParsingInput` which provides structured list fields
        and deterministic cleaning.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
    )

    job_title: str
    description: str
    requirements: str
    responsibilities: str


class JobParsingInput(BaseModel):
    """
    Cleaned, structured input for the LLM job parser.

    Requirements and responsibilities are split into individual items
    by the deterministic cleaning layer.  Exact duplicates are removed.
    All semantic qualifiers ("is a plus", "at least", "preferred",
    etc.) are preserved verbatim.

    The ``description`` is set to ``None`` when it merely restates the
    job title with no additional information.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
    )

    job_title: str = Field(
        min_length=1,
        max_length=300,
        description="Cleaned job title.",
    )

    description: str | None = Field(
        default=None,
        max_length=20_000,
        description=(
            "Cleaned description, or None when it merely restates "
            "the title."
        ),
    )

    requirements: list[str] = Field(
        default_factory=list,
        description="Individual requirement items.",
    )

    responsibilities: list[str] = Field(
        default_factory=list,
        description="Individual responsibility items.",
    )


class RawJobCreate(BaseModel):
    """
    Payload nhận từ form tạo job của HR.

    Model chấp nhận cả snake_case và camelCase để dễ tích hợp
    với frontend hiện tại.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=False,
        json_schema_extra={
            "example": {
                "job_title": "Backend Developer Intern",
                "location": "Ho Chi Minh City",
                "description": (
                    "We are looking for a Backend Developer Intern "
                    "to join our engineering team."
                ),
                "requirements": (
                    "- Basic knowledge of Python\n"
                    "- Understanding of relational databases\n"
                    "- Docker is a plus"
                ),
                "responsibilities": (
                    "- Assist in developing REST APIs\n"
                    "- Work with PostgreSQL\n"
                    "- Participate in code reviews"
                ),
                "employment_type": "early_career",
                "work_mode": "onsite",
                "salary_min": 3000000,
                "salary_max": 5000000,
                "deadline": "2026-07-31",
                "status": "draft",
            }
        },
    )

    job_title: str = Field(
        min_length=3,
        max_length=150,
        validation_alias=AliasChoices(
            "job_title",
            "jobTitle",
            "title",
        ),
    )

    location: str | None = Field(
        default=None,
        max_length=200,
    )

    # Draft được phép chưa nhập đủ nội dung.
    description: str = Field(
        default="",
        max_length=20_000,
    )

    requirements: str = Field(
        default="",
        max_length=20_000,
    )

    responsibilities: str = Field(
        default="",
        max_length=20_000,
    )

    employment_type: EmploymentType = Field(
        default=EmploymentType.EARLY_CAREER,
        validation_alias=AliasChoices(
            "employment_type",
            "employmentType",
        ),
    )

    work_mode: WorkMode = Field(
        default=WorkMode.ONSITE,
        validation_alias=AliasChoices(
            "work_mode",
            "workMode",
        ),
    )

    # Salary chỉ dùng để hiển thị và lọc job.
    # Không gửi vào AI và không dùng để rank CV.
    salary_min: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices(
            "salary_min",
            "salaryMin",
        ),
    )

    salary_max: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices(
            "salary_max",
            "salaryMax",
        ),
    )

    deadline: date | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "deadline",
            "application_deadline",
            "applicationDeadline",
        ),
    )

    status: JobStatus = JobStatus.DRAFT

    @field_validator("job_title")
    @classmethod
    def normalize_job_title(cls, value: str) -> str:
        cleaned = clean_single_line(value)

        if len(cleaned) < 3:
            raise ValueError(
                "job_title must contain at least 3 visible characters"
            )

        return cleaned

    @field_validator("location")
    @classmethod
    def normalize_location(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        cleaned = clean_single_line(value)

        return cleaned or None

    @field_validator(
        "description",
        "requirements",
        "responsibilities",
    )
    @classmethod
    def normalize_multiline_fields(
        cls,
        value: str,
    ) -> str:
        return clean_multiline(value)

    @model_validator(mode="after")
    def validate_salary_range(self) -> "RawJobCreate":
        """
        Salary có thể để trống.

        Nếu nhập cả min và max thì max không được nhỏ hơn min.
        """

        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError(
                "salary_max must be greater than or equal to salary_min"
            )

        return self

    @model_validator(mode="after")
    def validate_published_job(self) -> "RawJobCreate":
        """
        Draft có thể chưa hoàn chỉnh.

        Khi publish, job phải có tối thiểu:
        - description
        - requirements
        - deadline

        Responsibilities không bắt buộc vì HR có thể đã ghi
        nhiệm vụ trong description.
        """

        if self.status != JobStatus.PUBLISHED:
            return self

        missing_fields: list[str] = []

        if not self.description:
            missing_fields.append("description")

        if not self.requirements:
            missing_fields.append("requirements")

        if self.deadline is None:
            missing_fields.append("deadline")

        if (
            self.work_mode in {
                WorkMode.ONSITE,
                WorkMode.HYBRID,
            }
            and not self.location
        ):
            missing_fields.append("location")

        if missing_fields:
            raise ValueError(
                "Published job is missing required fields: "
                + ", ".join(missing_fields)
            )

        return self

    def to_parsing_input(self) -> JobParsingInput:
        """
        Build a cleaned, structured input for the LLM job parser.

        Deterministic cleaning is applied:
        - Bullet lists are split into individual items.
        - Exact duplicates are removed.
        - Description is set to None when it merely restates the title.
        - All semantic qualifiers are preserved.
        """
        cleaned_desc = clean_text_block(self.description)

        # Drop the description only when it contributes no information
        # beyond the job title itself.
        if not cleaned_desc or description_duplicates_title(
            cleaned_desc, self.job_title
        ):
            final_desc = None
        else:
            final_desc = cleaned_desc

        return JobParsingInput(
            job_title=self.job_title,
            description=final_desc,
            requirements=clean_to_list(self.requirements),
            responsibilities=clean_to_list(self.responsibilities),
        )

    def to_ai_input(self) -> JobEvaluationInput:
        """
        Tạo input dành riêng cho Qwen3-4B.

        .. deprecated::
            Kept for backward compatibility.  Prefer
            :meth:`to_parsing_input` for new code.
        """
        return JobEvaluationInput(
            job_title=self.job_title,
            description=self.description,
            requirements=self.requirements,
            responsibilities=self.responsibilities,
        )


class RawJobRecord(RawJobCreate):
    """
    Raw job sau khi backend đã lưu vào database.

    ID được để dạng string để tương thích cả UUID và các loại
    database ID khác.
    """

    job_id: str
    created_by: str

    created_at: datetime
    updated_at: datetime


class RawJobResponse(RawJobRecord):
    """
    Response trả về từ backend.

    Tách riêng khỏi RawJobRecord để sau này có thể thay đổi
    response mà không ảnh hưởng database model.
    """
    pass


# -------------------------------------------------------------------
# Output contracts for the future LLM parser
# -------------------------------------------------------------------

#: Allowed criterion categories.
CRITERION_TYPE = Literal[
    "technical_skill",
    "soft_skill",
    "responsibility",
    "experience",
    "education",
    "certification",
    "language",
    "domain_knowledge",
    "location",
    "work_authorization",
    "other",
]

#: Allowed importance levels.
IMPORTANCE = Literal["required", "preferred"]


class JobCriterion(BaseModel):
    """
    One structured criterion extracted from a job description.

    IDs are not assigned here — they will be generated by
    deterministic application code after validation and
    deduplication.
    """

    model_config = ConfigDict(extra="forbid")

    criterion_type: CRITERION_TYPE
    name: str = Field(min_length=1, max_length=300)
    canonical_name: str | None = Field(
        default=None,
        max_length=300,
        description=(
            "Optional normalized name for deduplication "
            "(e.g. 'python' for 'Python 3')."
        ),
    )
    importance: IMPORTANCE
    minimum_years: float | None = Field(
        default=None,
        ge=0,
        description="Minimum years of experience, if stated.",
    )
    proficiency: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Proficiency level when explicitly mentioned "
            "(e.g. 'intermediate', 'native', 'basic')."
        ),
    )
    source_text: str = Field(
        min_length=1,
        max_length=2000,
        description="Verbatim source fragment from the job posting.",
    )


class ParsedJobProfile(BaseModel):
    """
    Structured output produced by the future LLM job parser.

    This model represents the full parsed result for a single job
    posting.  It is the contract between the parser and the
    downstream matching/ranking system.
    """

    model_config = ConfigDict(extra="forbid")

    normalized_title: str = Field(
        min_length=1,
        max_length=300,
    )
    job_family: str | None = Field(
        default=None,
        max_length=200,
        description="Broad job family (e.g. 'software_engineering').",
    )
    seniority: str | None = Field(
        default=None,
        max_length=100,
        description="Seniority level (e.g. 'intern', 'junior', 'mid').",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Industry or domain tags.",
    )
    criteria: list[JobCriterion] = Field(
        default_factory=list,
        description="Extracted criteria from the job posting.",
    )
    search_keywords: list[str] = Field(
        default_factory=list,
        description="Additional keywords for search and retrieval.",
    )
