from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import models, schemas
from app.db.database import get_db
from app.dependencies import require_role

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=schemas.DashboardStats)
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    applications = (
        db.query(models.CandidateApplication)
        .filter(models.CandidateApplication.user_id == current_user.id)
        .order_by(models.CandidateApplication.created_at.desc())
        .all()
    )
    status_counts = {status: 0 for status in schemas.APPLICATION_STATUS_VALUES}
    for application in applications:
        status = str(application.application_status)
        status_counts[status] = status_counts.get(status, 0) + 1

    document_count = (
        db.query(models.Document).filter(models.Document.user_id == current_user.id).count()
    )

    application_ids = [application.id for application in applications]
    average_score = 0.0
    if application_ids:
        scores = [
            score
            for (score,) in db.query(models.AIAnalysisResult.match_score)
            .filter(models.AIAnalysisResult.application_id.in_(application_ids))
            .all()
        ]
        if scores:
            average_score = round(sum(scores) / len(scores), 1)

    return {
        "total_applications": len(applications),
        "applications_by_status": status_counts,
        "uploaded_documents": document_count,
        "average_ai_match_score": average_score,
        "recent_applications": applications[:5],
    }
