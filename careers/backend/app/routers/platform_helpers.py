from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models


def get_or_create_candidate_profile(db: Session, user: models.User) -> models.CandidateProfile:
    profile = (
        db.query(models.CandidateProfile).filter(models.CandidateProfile.user_id == user.id).first()
    )
    if profile:
        return profile

    profile = models.CandidateProfile(
        user_id=user.id,
        full_name=user.full_name,
    )
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        profile = (
            db.query(models.CandidateProfile)
            .filter(models.CandidateProfile.user_id == user.id)
            .first()
        )
        if profile:
            return profile
        raise
    db.refresh(profile)
    return profile


def serialize_company_summary(company: models.Company | None) -> dict | None:
    if not company:
        return None
    return {
        "id": company.id,
        "name": company.name,
        "industry": company.industry,
        "location": company.location,
        "website": company.website,
        "logo_url": company.logo_url,
    }


def serialize_company(company: models.Company | None) -> dict | None:
    summary = serialize_company_summary(company)
    if not summary or not company:
        return None
    return {
        **summary,
        "description": company.description,
        "owner_user_id": company.owner_user_id,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
    }


def serialize_job_posting(job: models.JobPosting) -> dict:
    return {
        "id": job.id,
        "company_id": job.company_id,
        "created_by_user_id": job.created_by_user_id,
        "title": job.title,
        "description": job.description,
        "requirements": job.requirements,
        "responsibilities": job.responsibilities,
        "location": job.location,
        "employment_type": job.employment_type,
        "work_mode": job.work_mode,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "deadline": job.deadline,
        "status": job.status,
        "version": job.version,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "company": serialize_company_summary(job.company),
        "ai_parse_status": job.ai_parse_status,
        "ai_parsed_profile": job.ai_parsed_profile,
        "ai_parse_error": job.ai_parse_error,
        "ai_parsed_at": job.ai_parsed_at,
        "ai_parse_revision": job.ai_parse_revision,
    }


def serialize_attached_document(link: models.JobApplicationDocument) -> dict:
    return {
        "id": link.id,
        "document_id": link.document_id,
        "document_type": link.document_type,
        "file_name": link.document.file_name,
        "created_at": link.created_at,
    }


def serialize_status_history(item: models.ApplicationStatusHistory) -> dict:
    return {
        "id": item.id,
        "old_status": item.old_status,
        "new_status": item.new_status,
        "changed_by_user_id": item.changed_by_user_id,
        "note": item.note,
        "created_at": item.created_at,
    }


def serialize_candidate_summary(user: models.User) -> dict:
    profile = user.candidate_profile
    profile_payload = None
    if profile:
        profile_payload = {
            "id": profile.id,
            "user_id": profile.user_id,
            "full_name": profile.full_name,
            "university": profile.university,
            "major": profile.major,
            "graduation_year": profile.graduation_year,
            "phone": profile.phone,
            "location": profile.location,
            "linkedin_url": profile.linkedin_url,
            "github_url": profile.github_url,
            "portfolio_url": profile.portfolio_url,
            "bio": profile.bio,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "profile": profile_payload,
    }


def serialize_job_application_summary(job_application: models.JobApplication) -> dict:
    return {
        "id": job_application.id,
        "job_posting_id": job_application.job_posting_id,
        "status": job_application.status,
        "version": job_application.version,
        "submitted_at": job_application.submitted_at,
        "updated_at": job_application.updated_at,
        "job_posting": serialize_job_posting(job_application.job_posting),
        "attached_documents_count": len(job_application.attached_documents),
    }


def serialize_job_application_detail(
    job_application: models.JobApplication,
    *,
    include_candidate: bool = False,
) -> dict:
    payload = {
        "id": job_application.id,
        "job_posting_id": job_application.job_posting_id,
        "candidate_user_id": job_application.candidate_user_id,
        "status": job_application.status,
        "version": job_application.version,
        "cover_letter_text": job_application.cover_letter_text,
        "candidate_note": job_application.candidate_note,
        "submitted_at": job_application.submitted_at,
        "updated_at": job_application.updated_at,
        "job_posting": serialize_job_posting(job_application.job_posting),
        "attached_documents": [
            serialize_attached_document(link) for link in job_application.attached_documents
        ],
        "status_history": [
            serialize_status_history(item) for item in job_application.status_history
        ],
    }
    if include_candidate:
        payload["candidate"] = serialize_candidate_summary(job_application.candidate_user)
        payload["ai_cv_parse_status"] = job_application.ai_cv_parse_status
        payload["ai_cv_parsed_profile"] = job_application.ai_cv_parsed_profile
        payload["ai_cv_parse_error"] = job_application.ai_cv_parse_error
        payload["ai_cv_parsed_at"] = job_application.ai_cv_parsed_at
        payload["ai_cv_parse_revision"] = job_application.ai_cv_parse_revision
    return payload
