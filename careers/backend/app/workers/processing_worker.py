import argparse
import logging
import os
import signal
import time
import uuid

from prometheus_client import start_http_server

from app.core.config import get_settings
from app.core.metrics import PROCESSING_JOB_DURATION_SECONDS, PROCESSING_WORKER_HEARTBEAT_TIMESTAMP
from app.db.database import SessionLocal
from app.services.processing_executors import execute_processing_job, record_processing_failure
from app.services.processing_jobs import (
    ProcessingJobError,
    claim_processing_jobs,
    mark_processing_job_retry_or_failed,
    mark_processing_job_succeeded,
    refresh_processing_gauges,
    utc_now,
)

logger = logging.getLogger(__name__)


class ShutdownState:
    def __init__(self) -> None:
        self.stop_requested = False

    def request_stop(self, _signum, _frame) -> None:
        self.stop_requested = True
        logger.info("processing_worker_shutdown_requested")


def run_once(
    *,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
    base_delay_seconds: int,
    max_delay_seconds: int,
) -> int:
    PROCESSING_WORKER_HEARTBEAT_TIMESTAMP.labels(worker_kind="processing").set(
        utc_now().timestamp()
    )
    claim_session = SessionLocal()
    try:
        claimed = claim_processing_jobs(
            claim_session,
            worker_id=worker_id,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
        )
        refresh_processing_gauges(claim_session)
        claim_session.commit()
    except Exception:
        claim_session.rollback()
        logger.exception("processing_claim_failed worker_id=%s", worker_id)
        raise
    finally:
        claim_session.close()

    for job in claimed:
        started = time.monotonic()
        outcome = "success"
        try:
            result_json = execute_processing_job(job)
            mark_session = SessionLocal()
            try:
                mark_processing_job_succeeded(
                    mark_session,
                    job_id=job.job_id,
                    result_json=result_json,
                )
                refresh_processing_gauges(mark_session)
                mark_session.commit()
            except Exception:
                mark_session.rollback()
                logger.exception(
                    "processing_mark_success_failed job_id=%s job_type=%s worker_id=%s",
                    job.job_id,
                    job.job_type,
                    worker_id,
                )
                raise
            finally:
                mark_session.close()
            logger.info(
                "processing_job_success job_id=%s job_type=%s attempt=%s worker_id=%s",
                job.job_id,
                job.job_type,
                job.attempts + 1,
                worker_id,
            )
        except ProcessingJobError as exc:
            retryable = exc.retryable
            error_code = exc.code
            error_message = str(exc)
            outcome = _mark_failure(
                job=job,
                worker_id=worker_id,
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
                base_delay_seconds=base_delay_seconds,
                max_delay_seconds=max_delay_seconds,
            )
        except Exception:
            outcome = _mark_failure(
                job=job,
                worker_id=worker_id,
                error_code="unexpected_error",
                error_message="Unexpected processing error.",
                retryable=True,
                base_delay_seconds=base_delay_seconds,
                max_delay_seconds=max_delay_seconds,
            )
            logger.exception(
                "processing_job_unexpected_error job_id=%s job_type=%s worker_id=%s",
                job.job_id,
                job.job_type,
                worker_id,
            )
        finally:
            PROCESSING_JOB_DURATION_SECONDS.labels(job_type=job.job_type, outcome=outcome).observe(
                time.monotonic() - started
            )
    return len(claimed)


def _mark_failure(
    *,
    job,
    worker_id: str,
    error_code: str,
    error_message: str,
    retryable: bool,
    base_delay_seconds: int,
    max_delay_seconds: int,
) -> str:
    mark_session = SessionLocal()
    try:
        retry_outcome = mark_processing_job_retry_or_failed(
            mark_session,
            job_id=job.job_id,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            base_delay_seconds=base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )
        refresh_processing_gauges(mark_session)
        mark_session.commit()
    except Exception:
        mark_session.rollback()
        logger.exception(
            "processing_mark_failure_failed job_id=%s job_type=%s worker_id=%s",
            job.job_id,
            job.job_type,
            worker_id,
        )
        raise
    finally:
        mark_session.close()

    terminal = retry_outcome == "failed"
    record_processing_failure(
        job,
        error_code=error_code,
        error_message=error_message,
        terminal=terminal,
    )
    log_method = logger.error if terminal else logger.warning
    log_method(
        "processing_job_failure job_id=%s job_type=%s attempt=%s worker_id=%s "
        "outcome=%s error_code=%s retryable=%s",
        job.job_id,
        job.job_type,
        job.attempts + 1,
        worker_id,
        retry_outcome,
        error_code,
        str(retryable).lower(),
    )
    return "failed" if terminal else "retry"


def run_continuously(
    *,
    worker_id: str,
    batch_size: int,
    poll_interval_seconds: float,
    lease_seconds: int,
    base_delay_seconds: int,
    max_delay_seconds: int,
    shutdown_state: ShutdownState,
) -> None:
    while not shutdown_state.stop_requested:
        claimed_count = run_once(
            worker_id=worker_id,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            base_delay_seconds=base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )
        if claimed_count == 0 and not shutdown_state.stop_requested:
            time.sleep(poll_interval_seconds)


def _build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Process async AI and document jobs.")
    parser.add_argument("--once", action="store_true", help="Run one claim/process iteration.")
    parser.add_argument("--batch-size", type=int, default=settings.PROCESSING_WORKER_BATCH_SIZE)
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=settings.PROCESSING_WORKER_POLL_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--lease-seconds", type=int, default=settings.PROCESSING_WORKER_LEASE_SECONDS
    )
    parser.add_argument(
        "--base-delay-seconds",
        type=int,
        default=settings.PROCESSING_WORKER_RETRY_BASE_DELAY_SECONDS,
    )
    parser.add_argument(
        "--max-delay-seconds",
        type=int,
        default=settings.PROCESSING_WORKER_RETRY_MAX_DELAY_SECONDS,
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=settings.PROCESSING_WORKER_METRICS_PORT,
        help="Prometheus metrics port for continuous mode; use 0 to disable.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    settings = get_settings()
    args = _build_parser().parse_args()
    worker_id = (
        settings.PROCESSING_WORKER_ID or os.environ.get("HOSTNAME") or f"processing-{uuid.uuid4()}"
    )
    shutdown_state = ShutdownState()
    signal.signal(signal.SIGTERM, shutdown_state.request_stop)
    signal.signal(signal.SIGINT, shutdown_state.request_stop)

    if args.once:
        run_once(
            worker_id=worker_id,
            batch_size=args.batch_size,
            lease_seconds=args.lease_seconds,
            base_delay_seconds=args.base_delay_seconds,
            max_delay_seconds=args.max_delay_seconds,
        )
        return

    if args.metrics_port > 0:
        start_http_server(args.metrics_port)
        logger.info(
            "processing_metrics_server_started worker_id=%s port=%s",
            worker_id,
            args.metrics_port,
        )

    run_continuously(
        worker_id=worker_id,
        batch_size=args.batch_size,
        poll_interval_seconds=args.poll_interval_seconds,
        lease_seconds=args.lease_seconds,
        base_delay_seconds=args.base_delay_seconds,
        max_delay_seconds=args.max_delay_seconds,
        shutdown_state=shutdown_state,
    )


if __name__ == "__main__":
    main()
