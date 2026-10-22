from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "fairenrol_careers_http_requests_total",
    "Total number of completed HTTP requests.",
    labelnames=[
        "method",
        "route",
        "status_code",
    ],
)


HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "fairenrol_careers_http_request_duration_seconds",
    "HTTP request processing duration in seconds.",
    labelnames=[
        "method",
        "route",
    ],
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)


HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "fairenrol_careers_http_requests_in_progress",
    "Current number of HTTP requests being processed.",
    labelnames=[
        "method",
    ],
)


DB_CONFLICT_TOTAL = Counter(
    "db_conflict_total",
    "Database write conflicts translated to application responses.",
    labelnames=[
        "entity_type",
        "operation",
    ],
)


UNIQUE_VIOLATION_TOTAL = Counter(
    "unique_violation_total",
    "Database unique constraint violations translated to 409 Conflict.",
    labelnames=[
        "entity_type",
        "operation",
    ],
)


IDEMPOTENCY_RESERVATION_TOTAL = Counter(
    "idempotency_reservation_total",
    "Idempotency key reservation attempts.",
    labelnames=[
        "operation",
        "result",
    ],
)


IDEMPOTENCY_REPLAY_TOTAL = Counter(
    "idempotency_replay_total",
    "Idempotent request replays served from persisted state.",
    labelnames=[
        "operation",
    ],
)


IDEMPOTENCY_MISMATCH_TOTAL = Counter(
    "idempotency_mismatch_total",
    "Idempotency key reuse attempts with a different request payload.",
    labelnames=[
        "operation",
    ],
)


IDEMPOTENCY_DUPLICATE_CONFLICT_TOTAL = Counter(
    "idempotency_duplicate_conflict_total",
    "Duplicate resource conflicts stored for idempotent commands.",
    labelnames=[
        "operation",
    ],
)


IDEMPOTENCY_EXECUTION_FAILURE_TOTAL = Counter(
    "idempotency_execution_failure_total",
    "Idempotent command execution failures after key reservation.",
    labelnames=[
        "operation",
        "error_type",
    ],
)


OPTIMISTIC_CONCURRENCY_TOTAL = Counter(
    "optimistic_concurrency_total",
    "Version-checked aggregate mutation outcomes.",
    labelnames=[
        "resource_type",
        "operation",
        "outcome",
    ],
)


WORKFLOW_COMMAND_TOTAL = Counter(
    "workflow_command_total",
    "Workflow command outcomes for version-checked aggregate commands.",
    labelnames=[
        "resource_type",
        "command",
        "outcome",
    ],
)


OUTBOX_EVENTS_ENQUEUED_TOTAL = Counter(
    "outbox_events_enqueued_total",
    "Transactional outbox events inserted with domain mutations.",
    labelnames=["event_family"],
)


OUTBOX_EVENTS_CLAIMED_TOTAL = Counter(
    "outbox_events_claimed_total",
    "Transactional outbox events claimed by dispatchers.",
    labelnames=["event_family"],
)


OUTBOX_PUBLISH_TOTAL = Counter(
    "outbox_publish_total",
    "Transactional outbox publish outcomes.",
    labelnames=["event_family", "outcome", "publisher"],
)


OUTBOX_RETRY_TOTAL = Counter(
    "outbox_retry_total",
    "Transactional outbox events scheduled for retry.",
    labelnames=["event_family", "publisher"],
)


OUTBOX_DEAD_TOTAL = Counter(
    "outbox_dead_total",
    "Transactional outbox events moved to the dead-letter state.",
    labelnames=["event_family", "publisher"],
)


OUTBOX_LEASE_RECLAIMED_TOTAL = Counter(
    "outbox_lease_reclaimed_total",
    "Expired transactional outbox leases reclaimed by dispatchers.",
    labelnames=["event_family"],
)


OUTBOX_TRANSPORT_ERROR_TOTAL = Counter(
    "outbox_transport_error_total",
    "Transactional outbox transport failures by bounded category.",
    labelnames=["event_family", "publisher", "error_category", "retryable"],
)


OUTBOX_PENDING_EVENTS = Gauge(
    "outbox_pending_events",
    "Pending transactional outbox events by bounded event family.",
    labelnames=["event_family"],
)


OUTBOX_DEAD_EVENTS = Gauge(
    "outbox_dead_events",
    "Dead-letter transactional outbox events by bounded event family.",
    labelnames=["event_family"],
)


OUTBOX_OLDEST_PENDING_AGE_SECONDS = Gauge(
    "outbox_oldest_pending_age_seconds",
    "Age of the oldest pending transactional outbox event.",
    labelnames=["event_family"],
)


OUTBOX_PUBLISH_DURATION_SECONDS = Histogram(
    "outbox_publish_duration_seconds",
    "Transactional outbox publish duration.",
    labelnames=["publisher", "outcome"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


OUTBOX_DISPATCHER_HEARTBEAT_TIMESTAMP = Gauge(
    "outbox_dispatcher_heartbeat_timestamp",
    "Unix timestamp for the last live heartbeat emitted by an outbox dispatcher.",
    labelnames=["publisher"],
)


OUTBOX_LAST_SUCCESSFUL_PUBLISH_TIMESTAMP = Gauge(
    "outbox_last_successful_publish_timestamp",
    "Unix timestamp for the last successful outbox publish by publisher.",
    labelnames=["publisher"],
)


PROCESSING_JOBS_ENQUEUED_TOTAL = Counter(
    "processing_jobs_enqueued_total",
    "Async processing jobs enqueued.",
    labelnames=["job_type"],
)


PROCESSING_JOBS_CLAIMED_TOTAL = Counter(
    "processing_jobs_claimed_total",
    "Async processing jobs claimed by workers.",
    labelnames=["job_type"],
)


PROCESSING_JOBS_SUCCEEDED_TOTAL = Counter(
    "processing_jobs_succeeded_total",
    "Async processing jobs completed successfully.",
    labelnames=["job_type"],
)


PROCESSING_JOBS_FAILED_TOTAL = Counter(
    "processing_jobs_failed_total",
    "Async processing jobs moved to a terminal failure state.",
    labelnames=["job_type", "error_code"],
)


PROCESSING_JOBS_RETRIED_TOTAL = Counter(
    "processing_jobs_retried_total",
    "Async processing jobs scheduled for retry.",
    labelnames=["job_type", "error_code"],
)


PROCESSING_JOBS_LEASE_RECLAIMED_TOTAL = Counter(
    "processing_jobs_lease_reclaimed_total",
    "Expired async processing job leases reclaimed by workers.",
    labelnames=["job_type"],
)


PROCESSING_QUEUE_DEPTH = Gauge(
    "processing_queue_depth",
    "Queued async processing jobs by bounded job type.",
    labelnames=["job_type"],
)


PROCESSING_OLDEST_QUEUED_AGE_SECONDS = Gauge(
    "processing_oldest_queued_age_seconds",
    "Age of the oldest queued async processing job by bounded job type.",
    labelnames=["job_type"],
)


PROCESSING_JOB_DURATION_SECONDS = Histogram(
    "processing_job_duration_seconds",
    "Async processing job execution duration.",
    labelnames=["job_type", "outcome"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)


AI_PROVIDER_DURATION_SECONDS = Histogram(
    "ai_provider_duration_seconds",
    "External AI provider call duration.",
    labelnames=["operation", "outcome"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)


AI_PROVIDER_FAILURES_TOTAL = Counter(
    "ai_provider_failures_total",
    "External AI provider failures.",
    labelnames=["operation", "error_code", "retryable"],
)


DOCUMENT_PROCESSING_FAILURES_TOTAL = Counter(
    "document_processing_failures_total",
    "Document-processing failures.",
    labelnames=["operation", "error_code"],
)


PROCESSING_WORKER_HEARTBEAT_TIMESTAMP = Gauge(
    "processing_worker_heartbeat_timestamp",
    "Unix timestamp for the last live heartbeat emitted by a processing worker.",
    labelnames=["worker_kind"],
)
