import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    PartialCredentialsError,
    ReadTimeoutError,
)

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

TransportErrorCategory = Literal[
    "configuration_error",
    "authentication_error",
    "authorization_error",
    "throttled",
    "timeout",
    "connection_error",
    "service_unavailable",
    "invalid_event",
    "unknown_transport_error",
]

TRANSPORT_ERROR_CATEGORIES: tuple[TransportErrorCategory, ...] = (
    "configuration_error",
    "authentication_error",
    "authorization_error",
    "throttled",
    "timeout",
    "connection_error",
    "service_unavailable",
    "invalid_event",
    "unknown_transport_error",
)

LOCAL_RUNTIME_ENVIRONMENTS = {"development", "dev", "local", "local-kubernetes", "test", "testing"}
TEST_RUNTIME_ENVIRONMENTS = {"test", "testing"}
LOCAL_PUBLISHERS = {"local", "logging"}
SUPPORTED_PUBLISHERS = LOCAL_PUBLISHERS | {"recording", "sqs"}


@dataclass(frozen=True)
class PublicationResult:
    accepted: bool
    detail: str | None = None
    retryable: bool = True
    error_category: TransportErrorCategory | None = None


@dataclass(frozen=True)
class TransportFailure:
    detail: str
    retryable: bool
    error_category: TransportErrorCategory


class OutboxPublisherConfigurationError(RuntimeError):
    pass


class OutboxPublisher(Protocol):
    name: str

    def publish(self, event_envelope: dict[str, Any]) -> PublicationResult: ...


class LoggingOutboxPublisher:
    name = "logging"

    def publish(self, event_envelope: dict[str, Any]) -> PublicationResult:
        logger.info(
            "outbox_event_local_publish event_id=%s event_type=%s aggregate_type=%s "
            "aggregate_id=%s publisher=%s outcome=success",
            event_envelope.get("eventId"),
            event_envelope.get("eventType"),
            event_envelope.get("aggregate", {}).get("type"),
            event_envelope.get("aggregate", {}).get("id"),
            self.name,
        )
        return PublicationResult(accepted=True)


class RecordingOutboxPublisher:
    name = "recording"

    def __init__(
        self,
        *,
        fail_first: int = 0,
        failure_message: str = "publish failed",
        retryable: bool = True,
        error_category: TransportErrorCategory = "unknown_transport_error",
    ) -> None:
        self.published: list[dict[str, Any]] = []
        self.fail_first = fail_first
        self.failure_message = failure_message
        self.retryable = retryable
        self.error_category = error_category

    def publish(self, event_envelope: dict[str, Any]) -> PublicationResult:
        if self.fail_first > 0:
            self.fail_first -= 1
            return PublicationResult(
                accepted=False,
                detail=self.failure_message,
                retryable=self.retryable,
                error_category=self.error_category,
            )
        self.published.append(event_envelope)
        return PublicationResult(accepted=True)


class SQSOutboxPublisher:
    name = "sqs"

    def __init__(
        self,
        *,
        queue_url: str,
        region_name: str,
        timeout_seconds: float,
        client: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        if not queue_url:
            raise OutboxPublisherConfigurationError(
                "OUTBOX_QUEUE_URL is required for SQS publisher"
            )
        self.queue_url = queue_url
        self.region_name = region_name
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._settings = settings or get_settings()

    @classmethod
    def from_settings(cls, settings: Settings) -> "SQSOutboxPublisher":
        return cls(
            queue_url=settings.OUTBOX_QUEUE_URL or "",
            region_name=settings.AWS_REGION,
            timeout_seconds=settings.OUTBOX_PUBLISH_TIMEOUT_SECONDS,
            settings=settings,
        )

    @property
    def client(self):
        if self._client is None:
            kwargs: dict[str, Any] = {
                "region_name": self.region_name,
                "config": BotoConfig(
                    connect_timeout=self.timeout_seconds,
                    read_timeout=self.timeout_seconds,
                    retries={"max_attempts": 0},
                ),
            }
            if self._settings.AWS_ACCESS_KEY_ID and self._settings.AWS_SECRET_ACCESS_KEY:
                kwargs["aws_access_key_id"] = self._settings.AWS_ACCESS_KEY_ID
                kwargs["aws_secret_access_key"] = self._settings.AWS_SECRET_ACCESS_KEY
            if self._settings.AWS_SESSION_TOKEN:
                kwargs["aws_session_token"] = self._settings.AWS_SESSION_TOKEN
            self._client = boto3.client("sqs", **kwargs)
        return self._client

    def publish(self, event_envelope: dict[str, Any]) -> PublicationResult:
        try:
            response = self.client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(
                    event_envelope,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                MessageAttributes=_message_attributes(event_envelope),
            )
        except Exception as exc:
            failure = classify_transport_error(exc)
            logger.warning(
                "outbox_transport_publish_failed event_id=%s event_type=%s aggregate_type=%s "
                "aggregate_id=%s publisher=%s outcome=rejected error_category=%s retryable=%s",
                event_envelope.get("eventId"),
                event_envelope.get("eventType"),
                event_envelope.get("aggregate", {}).get("type"),
                event_envelope.get("aggregate", {}).get("id"),
                self.name,
                failure.error_category,
                str(failure.retryable).lower(),
            )
            return PublicationResult(
                accepted=False,
                detail=failure.detail,
                retryable=failure.retryable,
                error_category=failure.error_category,
            )

        return PublicationResult(accepted=True, detail=response.get("MessageId"))


def _string_attribute(value: object) -> dict[str, str]:
    return {"DataType": "String", "StringValue": str(value)}


def _message_attributes(event_envelope: dict[str, Any]) -> dict[str, dict[str, str]]:
    aggregate = event_envelope.get("aggregate") or {}
    attributes = {
        "eventId": _string_attribute(event_envelope.get("eventId", "")),
        "eventType": _string_attribute(event_envelope.get("eventType", "")),
        "schemaVersion": _string_attribute(event_envelope.get("schemaVersion", "")),
        "aggregateType": _string_attribute(aggregate.get("type", "")),
        "aggregateId": _string_attribute(aggregate.get("id", "")),
    }
    correlation_id = event_envelope.get("correlationId")
    if correlation_id:
        attributes["correlationId"] = _string_attribute(correlation_id)
    return attributes


def classify_transport_error(exc: BaseException) -> TransportFailure:
    if isinstance(exc, (NoCredentialsError, PartialCredentialsError)):
        return _failure(exc, retryable=False, error_category="authentication_error")
    if isinstance(exc, (ConnectTimeoutError, ReadTimeoutError)):
        return _failure(exc, retryable=True, error_category="timeout")
    if isinstance(exc, (EndpointConnectionError, ConnectionClosedError)):
        return _failure(exc, retryable=True, error_category="connection_error")
    if isinstance(exc, ClientError):
        return _classify_client_error(exc)
    if isinstance(exc, BotoCoreError):
        return _failure(exc, retryable=True, error_category="unknown_transport_error")
    return _failure(exc, retryable=True, error_category="unknown_transport_error")


def _classify_client_error(exc: ClientError) -> TransportFailure:
    response = exc.response or {}
    error = response.get("Error", {})
    code = str(error.get("Code", ""))
    status_code = int(response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)

    throttled_codes = {
        "Throttling",
        "ThrottlingException",
        "TooManyRequestsException",
        "RequestThrottled",
        "RequestThrottledException",
        "RequestLimitExceeded",
    }
    authentication_codes = {
        "AuthFailure",
        "ExpiredToken",
        "InvalidAccessKeyId",
        "InvalidClientTokenId",
        "InvalidToken",
        "SignatureDoesNotMatch",
        "UnrecognizedClientException",
    }
    authorization_codes = {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedOperation",
    }
    configuration_codes = {
        "AWS.SimpleQueueService.NonExistentQueue",
        "InvalidAddress",
        "QueueDoesNotExist",
    }
    invalid_event_codes = {
        "InvalidMessageContents",
        "InvalidParameterCombination",
        "InvalidParameterValue",
        "MissingParameter",
    }
    service_unavailable_codes = {
        "InternalError",
        "InternalFailure",
        "ServiceUnavailable",
    }

    if code in throttled_codes or status_code == 429:
        return _failure(exc, retryable=True, error_category="throttled")
    if code in authentication_codes:
        return _failure(exc, retryable=False, error_category="authentication_error")
    if code in authorization_codes:
        return _failure(exc, retryable=False, error_category="authorization_error")
    if code in configuration_codes:
        return _failure(exc, retryable=False, error_category="configuration_error")
    if code in invalid_event_codes:
        return _failure(exc, retryable=False, error_category="invalid_event")
    if status_code in {408, 504}:
        return _failure(exc, retryable=True, error_category="timeout")
    if code in service_unavailable_codes or status_code >= 500:
        return _failure(exc, retryable=True, error_category="service_unavailable")
    return _failure(exc, retryable=True, error_category="unknown_transport_error")


def _failure(
    exc: BaseException,
    *,
    retryable: bool,
    error_category: TransportErrorCategory,
) -> TransportFailure:
    return TransportFailure(
        detail=str(exc),
        retryable=retryable,
        error_category=error_category,
    )


def get_outbox_publisher(name: str | None = None) -> OutboxPublisher:
    settings = get_settings()
    publisher_name = (name or settings.OUTBOX_PUBLISHER).strip().lower()
    environment = settings.runtime_environment

    if publisher_name not in SUPPORTED_PUBLISHERS:
        raise OutboxPublisherConfigurationError(
            f"Unsupported OUTBOX_PUBLISHER adapter: {publisher_name}"
        )
    if publisher_name in LOCAL_PUBLISHERS and environment not in LOCAL_RUNTIME_ENVIRONMENTS:
        raise OutboxPublisherConfigurationError(
            "OUTBOX_PUBLISHER=logging is local-only. Use OUTBOX_PUBLISHER=sqs outside local "
            "development."
        )
    if publisher_name == "recording" and environment not in TEST_RUNTIME_ENVIRONMENTS:
        raise OutboxPublisherConfigurationError(
            "OUTBOX_PUBLISHER=recording is test-only. Use OUTBOX_PUBLISHER=logging locally or "
            "OUTBOX_PUBLISHER=sqs for production-like runtimes."
        )
    if settings.is_production_runtime and publisher_name != "sqs":
        raise OutboxPublisherConfigurationError(
            "Production outbox dispatch requires OUTBOX_PUBLISHER=sqs."
        )
    if publisher_name in LOCAL_PUBLISHERS:
        return LoggingOutboxPublisher()
    if publisher_name == "recording":
        return RecordingOutboxPublisher()
    return SQSOutboxPublisher.from_settings(settings)
