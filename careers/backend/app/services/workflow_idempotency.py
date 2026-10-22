from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.metrics import IDEMPOTENCY_EXECUTION_FAILURE_TOTAL
from app.db import models
from app.services.idempotency_service import (
    complete_idempotency_record,
    deterministic_request_hash,
    error_response_body,
    normalize_idempotency_key,
    reserve_idempotency_record,
)
from app.services.workflow_commands import record_workflow_outcome


def workflow_command_scope(
    *,
    resource_type: str,
    resource_id: int,
    command: str,
    actor_id: int,
) -> str:
    return f"{resource_type}:{resource_id}:{command}:actor:{actor_id}"


def workflow_command_request_hash(
    *,
    resource_type: str,
    resource_id: int,
    command: str,
    payload: dict[str, Any],
) -> str:
    return deterministic_request_hash(
        {
            "operation": "workflow_command",
            "resource_type": resource_type,
            "resource_id": resource_id,
            "command": command,
            "payload": payload,
        }
    )


def run_workflow_command_with_optional_idempotency(
    db: Session,
    *,
    idempotency_key: str | None,
    resource_type: str,
    resource_id: int,
    command: str,
    actor: models.User,
    payload: dict[str, Any],
    execute: Callable[[], dict[str, Any]],
) -> dict[str, Any] | JSONResponse:
    if idempotency_key is None:
        try:
            response_body = execute()
            db.commit()
            return response_body
        except HTTPException:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise

    normalized_key = normalize_idempotency_key(idempotency_key)
    scope = workflow_command_scope(
        resource_type=resource_type,
        resource_id=resource_id,
        command=command,
        actor_id=actor.id,
    )
    request_hash = workflow_command_request_hash(
        resource_type=resource_type,
        resource_id=resource_id,
        command=command,
        payload=payload,
    )
    reserved = reserve_idempotency_record(
        db,
        scope=scope,
        idempotency_key=normalized_key,
        request_hash=request_hash,
        operation=command,
    )
    if isinstance(reserved, JSONResponse):
        record_workflow_outcome(
            resource_type=resource_type,
            command=command,
            outcome="replay",
        )
        return reserved

    try:
        response_body = execute()
        completed_body = complete_idempotency_record(
            reserved,
            response_status=status.HTTP_200_OK,
            response_body=response_body,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        db.commit()
        return completed_body
    except HTTPException as exc:
        complete_idempotency_record(
            reserved,
            response_status=exc.status_code,
            response_body=error_response_body(exc),
            resource_type=resource_type,
            resource_id=resource_id,
        )
        db.commit()
        raise exc
    except Exception:
        db.rollback()
        IDEMPOTENCY_EXECUTION_FAILURE_TOTAL.labels(
            operation=command,
            error_type="unexpected",
        ).inc()
        raise
