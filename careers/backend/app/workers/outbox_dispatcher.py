import argparse
import logging
import os
import signal
import time
import uuid

from prometheus_client import start_http_server

from app.core.config import get_settings
from app.core.metrics import (
    OUTBOX_DISPATCHER_HEARTBEAT_TIMESTAMP,
    OUTBOX_LAST_SUCCESSFUL_PUBLISH_TIMESTAMP,
    OUTBOX_PUBLISH_DURATION_SECONDS,
)
from app.db.database import SessionLocal
from app.services.outbox import (
    claim_outbox_events,
    mark_event_published,
    mark_event_retry_or_dead,
    refresh_outbox_gauges,
    utc_now,
)
from app.services.outbox_publishers import OutboxPublisher, get_outbox_publisher

logger = logging.getLogger(__name__)


class ShutdownState:
    def __init__(self) -> None:
        self.stop_requested = False

    def request_stop(self, _signum, _frame) -> None:
        self.stop_requested = True
        logger.info("outbox_dispatcher_shutdown_requested")


def run_once(
    *,
    publisher: OutboxPublisher,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
    max_attempts: int,
    base_delay_seconds: int,
    max_delay_seconds: int,
) -> int:
    OUTBOX_DISPATCHER_HEARTBEAT_TIMESTAMP.labels(publisher=publisher.name).set(
        utc_now().timestamp()
    )
    claim_session = SessionLocal()
    try:
        claimed = claim_outbox_events(
            claim_session,
            worker_id=worker_id,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
        )
        claim_session.commit()
    except Exception:
        claim_session.rollback()
        logger.exception("outbox_claim_failed worker_id=%s", worker_id)
        raise
    finally:
        claim_session.close()

    for event in claimed:
        started = time.monotonic()
        outcome = "success"
        failure_error: BaseException | str | None = None
        error_category = "unknown_transport_error"
        retryable = True
        try:
            result = publisher.publish(event.payload)
            if not result.accepted:
                failure_error = result.detail or "publisher rejected event"
                error_category = result.error_category or "unknown_transport_error"
                retryable = result.retryable
            else:
                mark_session = SessionLocal()
                try:
                    mark_event_published(
                        mark_session,
                        event_id=event.event_id,
                        publisher=publisher.name,
                    )
                    refresh_outbox_gauges(mark_session)
                    mark_session.commit()
                    OUTBOX_LAST_SUCCESSFUL_PUBLISH_TIMESTAMP.labels(publisher=publisher.name).set(
                        utc_now().timestamp()
                    )
                except Exception:
                    mark_session.rollback()
                    logger.exception(
                        "outbox_mark_published_failed event_id=%s event_type=%s "
                        "worker_id=%s publisher=%s",
                        event.event_id,
                        event.event_type,
                        worker_id,
                        publisher.name,
                    )
                    raise
                finally:
                    mark_session.close()
                logger.info(
                    "outbox_publish_success event_id=%s event_type=%s aggregate_type=%s "
                    "aggregate_id=%s attempt=%s worker_id=%s publisher=%s outcome=success",
                    event.event_id,
                    event.event_type,
                    event.aggregate_type,
                    event.aggregate_id,
                    event.attempts + 1,
                    worker_id,
                    publisher.name,
                )
        except Exception as exc:
            failure_error = exc

        if failure_error is not None:
            retry_session = SessionLocal()
            try:
                retry_outcome = mark_event_retry_or_dead(
                    retry_session,
                    event_id=event.event_id,
                    publisher=publisher.name,
                    error=failure_error,
                    error_category=error_category,
                    retryable=retryable,
                    max_attempts=max_attempts,
                    base_delay_seconds=base_delay_seconds,
                    max_delay_seconds=max_delay_seconds,
                )
                refresh_outbox_gauges(retry_session)
                retry_session.commit()
            except Exception:
                retry_session.rollback()
                logger.exception(
                    "outbox_retry_mark_failed event_id=%s event_type=%s worker_id=%s",
                    event.event_id,
                    event.event_type,
                    worker_id,
                )
                raise
            finally:
                retry_session.close()
            outcome = "dead" if retry_outcome == "dead" else "retry"
            log_method = logger.error if retry_outcome == "dead" else logger.warning
            log_method(
                "outbox_publish_failure event_id=%s event_type=%s aggregate_type=%s "
                "aggregate_id=%s attempt=%s worker_id=%s publisher=%s outcome=%s "
                "error_category=%s retryable=%s",
                event.event_id,
                event.event_type,
                event.aggregate_type,
                event.aggregate_id,
                event.attempts + 1,
                worker_id,
                publisher.name,
                outcome,
                error_category,
                str(retryable).lower(),
            )
        OUTBOX_PUBLISH_DURATION_SECONDS.labels(
            publisher=publisher.name,
            outcome=outcome,
        ).observe(time.monotonic() - started)
    return len(claimed)


def run_continuously(
    *,
    publisher: OutboxPublisher,
    worker_id: str,
    batch_size: int,
    poll_interval_seconds: float,
    lease_seconds: int,
    max_attempts: int,
    base_delay_seconds: int,
    max_delay_seconds: int,
    shutdown_state: ShutdownState,
) -> None:
    while not shutdown_state.stop_requested:
        claimed_count = run_once(
            publisher=publisher,
            worker_id=worker_id,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            base_delay_seconds=base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )
        if claimed_count == 0 and not shutdown_state.stop_requested:
            time.sleep(poll_interval_seconds)


def _build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Dispatch transactional outbox events.")
    parser.add_argument("--once", action="store_true", help="Run one claim/publish iteration.")
    parser.add_argument("--publisher", default=settings.OUTBOX_PUBLISHER)
    parser.add_argument("--batch-size", type=int, default=settings.OUTBOX_BATCH_SIZE)
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=settings.OUTBOX_POLL_INTERVAL_SECONDS,
    )
    parser.add_argument("--lease-seconds", type=int, default=settings.OUTBOX_LEASE_SECONDS)
    parser.add_argument("--max-attempts", type=int, default=settings.OUTBOX_MAX_ATTEMPTS)
    parser.add_argument(
        "--base-delay-seconds",
        type=int,
        default=settings.OUTBOX_RETRY_BASE_DELAY_SECONDS,
    )
    parser.add_argument(
        "--max-delay-seconds",
        type=int,
        default=settings.OUTBOX_RETRY_MAX_DELAY_SECONDS,
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=settings.OUTBOX_METRICS_PORT,
        help="Prometheus metrics port for continuous mode; use 0 to disable.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    settings = get_settings()
    args = _build_parser().parse_args()

    worker_id = settings.OUTBOX_WORKER_ID or os.environ.get("HOSTNAME") or f"outbox-{uuid.uuid4()}"
    publisher = get_outbox_publisher(args.publisher)
    shutdown_state = ShutdownState()
    signal.signal(signal.SIGTERM, shutdown_state.request_stop)
    signal.signal(signal.SIGINT, shutdown_state.request_stop)

    if args.once:
        run_once(
            publisher=publisher,
            worker_id=worker_id,
            batch_size=args.batch_size,
            lease_seconds=args.lease_seconds,
            max_attempts=args.max_attempts,
            base_delay_seconds=args.base_delay_seconds,
            max_delay_seconds=args.max_delay_seconds,
        )
        return

    if args.metrics_port > 0:
        start_http_server(args.metrics_port)
        logger.info(
            "outbox_metrics_server_started worker_id=%s publisher=%s port=%s",
            worker_id,
            publisher.name,
            args.metrics_port,
        )

    run_continuously(
        publisher=publisher,
        worker_id=worker_id,
        batch_size=args.batch_size,
        poll_interval_seconds=args.poll_interval_seconds,
        lease_seconds=args.lease_seconds,
        max_attempts=args.max_attempts,
        base_delay_seconds=args.base_delay_seconds,
        max_delay_seconds=args.max_delay_seconds,
        shutdown_state=shutdown_state,
    )


if __name__ == "__main__":
    main()
