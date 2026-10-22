from typing import Literal
from pydantic import BaseModel, Field

class CVParsingInput(BaseModel):
    document_text: str

class CandidateEvidence(BaseModel):
    evidence_type: Literal[
        "technical_skill",
        "soft_skill",
        "work_experience",
        "project_experience",
        "research_experience",
        "education",
        "certification",
        "language",
        "achievement",
        "activity",
        "availability",
        "other",
    ]
    name: str
    canonical_name: str | None = None
    description: str | None = None
    organization: str | None = None
    role: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    skills: list[str] = Field(default_factory=list)
    source_text: str

class CandidateProfile(BaseModel):
    headline: str | None = None
    summary: str | None = None
    evidence_items: list[CandidateEvidence] = Field(default_factory=list)
    search_keywords: list[str] = Field(default_factory=list)
