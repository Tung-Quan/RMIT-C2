from collections.abc import Callable
import hashlib

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db import models
from app.db.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = getattr(request.state, "tide_identity", None)
    if not payload:
        raise credentials_exception

    identity_key = hashlib.sha256((payload["tide_issuer"] + "\0" + payload["tide_subject"]).encode()).hexdigest()
    user = db.query(models.User).filter_by(tide_identity_key=identity_key).first()
    if user is None:
        user = models.User(tide_identity_key=identity_key, email=payload.get("email"), full_name=payload["full_name"], role=payload["role"], hashed_password=None)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.query(models.User).filter_by(tide_identity_key=identity_key).first()
            if user is None:
                raise HTTPException(status_code=409, detail="An existing account needs an explicit identity binding")
        db.refresh(user)

    if not user or not user.is_active:
        raise credentials_exception
    if user.role != payload["role"]:
        user.role = payload["role"]
        db.commit()
    return user


def require_role(*allowed_roles: str) -> Callable:
    def dependency(
        current_user: models.User = Depends(get_current_user),
    ) -> models.User:
        # Hiring staff retain the ordinary self-owned candidate workspace too.
        candidate_access = "candidate" in allowed_roles and current_user.role == "hr"
        if current_user.role not in allowed_roles and not candidate_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return current_user

    return dependency


def require_application_owner(
    application_id: int,
    db: Session,
    current_user: models.User,
) -> models.CandidateApplication:
    application = db.get(models.CandidateApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this application",
        )
    return application


def require_company_owner_or_member(
    company_id: int,
    db: Session,
    current_user: models.User,
) -> models.Company:
    company = db.get(models.Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if company.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this company",
        )
    return company


def require_job_owner(
    job_id: int,
    db: Session,
    current_user: models.User,
) -> models.JobPosting:
    job = db.get(models.JobPosting, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    company = db.get(models.Company, job.company_id)
    if not company or company.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this job",
        )
    return job


def require_candidate_job_application(
    application_id: int,
    db: Session,
    current_user: models.User,
) -> models.JobApplication:
    job_application = db.get(models.JobApplication, application_id)
    if not job_application:
        raise HTTPException(status_code=404, detail="Job application not found")
    if job_application.candidate_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this job application",
        )
    return job_application


def require_hr_job_application(
    application_id: int,
    db: Session,
    current_user: models.User,
) -> models.JobApplication:
    job_application = db.get(models.JobApplication, application_id)
    if not job_application:
        raise HTTPException(status_code=404, detail="Job application not found")
    job = db.get(models.JobPosting, job_application.job_posting_id)
    company = db.get(models.Company, job.company_id) if job else None
    if not job or not company or company.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this job application",
        )
    return job_application
