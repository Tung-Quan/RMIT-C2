import logging
from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.metrics import DB_CONFLICT_TOTAL, UNIQUE_VIOLATION_TOTAL

logger = logging.getLogger(__name__)


def record_integrity_conflict(
    *,
    entity_type: str,
    operation: str,
) -> None:
    DB_CONFLICT_TOTAL.labels(entity_type=entity_type, operation=operation).inc()
    UNIQUE_VIOLATION_TOTAL.labels(entity_type=entity_type, operation=operation).inc()
    logger.info(
        "database_integrity_conflict entity_type=%s operation=%s",
        entity_type,
        operation,
    )


def raise_integrity_conflict(
    db: Session,
    exc: IntegrityError,
    *,
    detail: str,
    entity_type: str,
    operation: str,
) -> NoReturn:
    db.rollback()
    record_integrity_conflict(entity_type=entity_type, operation=operation)
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
