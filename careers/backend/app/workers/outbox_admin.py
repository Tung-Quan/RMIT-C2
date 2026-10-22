import argparse
import logging
import sys
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db import models
from app.db.database import SessionLocal
from app.services.outbox import (
    OUTBOX_STATUS_DEAD,
    cleanup_published_events,
    event_family_from_aggregate_type,
    requeue_dead_event,
    utc_now,
)

logger = logging.getLogger(__name__)


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("event id must be a UUID") from exc


def _build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Operate transactional outbox dead events.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_dead = subparsers.add_parser("list-dead", help="List bounded DEAD outbox events.")
    list_dead.add_argument("--limit", type=int, default=50)

    requeue = subparsers.add_parser("requeue", help="Requeue one DEAD outbox event.")
    requeue.add_argument("--event-id", required=True, type=_uuid)

    cleanup = subparsers.add_parser(
        "cleanup-published",
        help="Delete old PUBLISHED outbox events.",
    )
    cleanup.add_argument(
        "--older-than-days",
        type=int,
        default=settings.OUTBOX_PUBLISHED_RETENTION_DAYS,
    )
    cleanup.add_argument("--batch-size", type=int, default=500)

    return parser


def _bounded_error(value: str | None) -> str:
    if not value:
        return ""
    return value if len(value) <= 120 else value[:117] + "..."


def _list_dead(limit: int) -> int:
    if limit <= 0 or limit > 500:
        print("limit must be between 1 and 500", file=sys.stderr)
        return 2
    session = SessionLocal()
    try:
        rows = (
            session.execute(
                select(models.OutboxEvent)
                .where(models.OutboxEvent.status == OUTBOX_STATUS_DEAD)
                .order_by(models.OutboxEvent.created_at.asc(), models.OutboxEvent.id.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        if not rows:
            print("no dead events")
            return 0
        for event in rows:
            event_family = event_family_from_aggregate_type(event.aggregate_type)
            created_at = event.created_at.isoformat()
            last_error = _bounded_error(event.last_error)
            print(
                f"event_id={event.id} event_type={event.event_type} "
                f"event_family={event_family} aggregate_type={event.aggregate_type} "
                f"aggregate_id={event.aggregate_id} attempts={event.attempts} "
                f"created_at={created_at} last_error={last_error}"
            )
        return 0
    finally:
        session.close()


def _requeue(event_id: str) -> int:
    session = SessionLocal()
    try:
        requeued = requeue_dead_event(session, event_id=event_id)
        if not requeued:
            session.rollback()
            print(f"event_id={event_id} requeued=0", file=sys.stderr)
            return 1
        session.commit()
        print(f"event_id={event_id} requeued=1")
        return 0
    except Exception:
        session.rollback()
        logger.exception("outbox_admin_requeue_failed event_id=%s", event_id)
        raise
    finally:
        session.close()


def _cleanup_published(*, older_than_days: int, batch_size: int) -> int:
    if older_than_days < 1:
        print("older-than-days must be at least 1", file=sys.stderr)
        return 2
    if batch_size <= 0 or batch_size > 5000:
        print("batch-size must be between 1 and 5000", file=sys.stderr)
        return 2
    session = SessionLocal()
    try:
        cutoff = utc_now() - timedelta(days=older_than_days)
        count = cleanup_published_events(
            session,
            older_than=cutoff,
            batch_size=batch_size,
        )
        session.commit()
        print(f"deleted={count} older_than_days={older_than_days}")
        return 0
    except Exception:
        session.rollback()
        logger.exception("outbox_admin_cleanup_published_failed")
        raise
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level="INFO")
    args = _build_parser().parse_args(argv)
    if args.command == "list-dead":
        return _list_dead(args.limit)
    if args.command == "requeue":
        return _requeue(args.event_id)
    if args.command == "cleanup-published":
        return _cleanup_published(
            older_than_days=args.older_than_days,
            batch_size=args.batch_size,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
