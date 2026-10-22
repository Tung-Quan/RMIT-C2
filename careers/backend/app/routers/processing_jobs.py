from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import models, schemas
from app.db.database import get_db
from app.dependencies import require_role
from app.services.processing_jobs import get_authorized_processing_job, processing_job_payload

router = APIRouter(tags=["processing-jobs"])


@router.get("/processing-jobs/{job_id}", response_model=schemas.ProcessingJobRead)
def get_processing_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "hr", "admin")),
):
    job = get_authorized_processing_job(db, job_id=job_id, current_user=current_user)
    return processing_job_payload(job)
