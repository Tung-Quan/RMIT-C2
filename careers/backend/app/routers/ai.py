import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import models, schemas
from app.db.database import get_db
from app.dependencies import require_role
from app.routers.applications import get_owned_application
from app.services.ai_service import analyze_match, generate_interview_questions
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ai"])


@router.post(
    "/applications/{application_id}/ai/analyze",
    response_model=schemas.AIAnalysisRead,
    status_code=status.HTTP_201_CREATED,
)
def analyze_application(
    application_id: int,
    payload: schemas.AIAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    application = get_owned_application(db, application_id, int(current_user.id))
    cv_text = payload.cv_text

    if payload.document_id:
        document = (
            db.query(models.Document)
            .filter(
                models.Document.id == payload.document_id,
                models.Document.user_id == current_user.id,
                models.Document.application_id == application_id,
            )
            .first()
        )
        if not document:
            raise HTTPException(status_code=404, detail="CV document not found")
        if document.document_type != "CV" or Path(document.file_name).suffix.lower() != ".txt":
            raise HTTPException(
                status_code=400,
                detail="Only uploaded .txt CV documents can be analyzed",
            )
        cv_text = StorageService().read_text_file(str(document.s3_key))

    if not cv_text:
        raise HTTPException(status_code=400, detail="CV text is required")

    result = analyze_match(
        cv_text=cv_text,
        job_description=str(application.job_description),
        company_name=str(application.company_name),
        position_title=str(application.position_title),
    )
    analysis = models.AIAnalysisResult(
        application_id=application_id,
        cv_text=cv_text,
        job_description=application.job_description,
        **result,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    logger.info(
        "ai_analysis_created user_id=%s application_id=%s score=%s",
        current_user.id,
        application_id,
        analysis.match_score,
    )
    return analysis


@router.get("/applications/{application_id}/ai/result", response_model=schemas.AIAnalysisRead)
def get_latest_ai_result(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    get_owned_application(db, application_id, int(current_user.id))
    result = (
        db.query(models.AIAnalysisResult)
        .filter(models.AIAnalysisResult.application_id == application_id)
        .order_by(models.AIAnalysisResult.created_at.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="AI analysis result not found")
    return result


@router.post(
    "/applications/{application_id}/ai/interview-questions",
    response_model=list[schemas.InterviewQuestionRead],
    status_code=status.HTTP_201_CREATED,
)
def create_interview_questions(
    application_id: int,
    count: int = Query(default=5, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("candidate", "admin")),
):
    application = get_owned_application(db, application_id, int(current_user.id))
    latest_result = (
        db.query(models.AIAnalysisResult)
        .filter(models.AIAnalysisResult.application_id == application_id)
        .order_by(models.AIAnalysisResult.created_at.desc())
        .first()
    )
    generated = generate_interview_questions(
        str(application.job_description),
        missing_skills=list(latest_result.missing_skills)
        if latest_result and latest_result.missing_skills
        else None,
        count=count,
    )
    questions = [
        models.InterviewQuestion(
            application_id=application_id,
            question=item["question"],
            answer_hint=item["answer_hint"],
        )
        for item in generated
    ]
    db.add_all(questions)
    db.commit()
    for question in questions:
        db.refresh(question)
    logger.info(
        "interview_questions_created user_id=%s application_id=%s count=%s",
        current_user.id,
        application_id,
        len(questions),
    )
    return questions
