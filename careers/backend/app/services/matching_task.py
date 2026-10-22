import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db import models

logger = logging.getLogger(__name__)


def get_session():
    engine = create_engine(get_settings().DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def background_match_applications(rerank_run_id: int) -> None:
    db = get_session()
    try:
        run = db.query(models.JobRerankRun).filter(models.JobRerankRun.id == rerank_run_id).first()
        if not run:
            logger.error(f"JobRerankRun {rerank_run_id} not found.")
            return

        run.status = "processing"
        db.commit()

        job = run.job_posting
        if not job or job.ai_parse_status != "completed" or not job.ai_parsed_profile:
            run.status = "failed"
            run.error_message = "Job not parsed."
            run.completed_at = datetime.now(UTC)
            db.commit()
            return

        # Fetch applications with parsed CVs
        applications = (
            db.query(models.JobApplication)
            .filter(
                models.JobApplication.job_posting_id == job.id,
                models.JobApplication.ai_cv_parse_status == "completed",
                models.JobApplication.ai_cv_parsed_profile.isnot(None),
            )
            .all()
        )

        if not applications:
            run.status = "completed"
            run.model_name = "None"
            run.completed_at = datetime.now(UTC)
            db.commit()
            return

        app_requests = []
        for app in applications:
            app_requests.append(
                {
                    "application_id": app.id,
                    "cv_parse_revision": app.ai_cv_parse_revision,
                    "candidate_profile": app.ai_cv_parsed_profile,
                }
            )

        payload = {"job_profile": job.ai_parsed_profile, "applications": app_requests}

        # Call AI service
        settings = get_settings()
        url = f"{settings.AI_SERVICE_BASE_URL.rstrip('/')}/match-applications"
        headers: dict[str, str] = {}
        ai_service_key = getattr(settings, "AI_SERVICE_API_KEY", None)
        if ai_service_key:
            headers["X-AI-Service-Key"] = ai_service_key

        timeout = 600.0  # Matching can take some time

        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        run.model_name = data.get("model_name")

        results = data.get("results", [])

        for result in results:
            app_id = result["application_id"]
            crit_results = result["criterion_results"]

            # Upsert ApplicationRerankResult
            existing = (
                db.query(models.ApplicationRerankResult)
                .filter(
                    models.ApplicationRerankResult.rerank_run_id == run.id,
                    models.ApplicationRerankResult.job_application_id == app_id,
                )
                .first()
            )

            if existing:
                existing.criterion_results_json = crit_results
            else:
                new_result = models.ApplicationRerankResult(
                    rerank_run_id=run.id,
                    job_application_id=app_id,
                    criterion_results_json=crit_results,
                )
                db.add(new_result)

        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        db.commit()

    except Exception as e:
        logger.error(f"Error matching applications: {e}", exc_info=True)
        if "db" in locals() and "run" in locals():
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(UTC)
            db.commit()
    finally:
        if "db" in locals():
            db.close()
