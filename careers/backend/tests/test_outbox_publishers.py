import json

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from app.core.config import get_settings
from app.services.outbox_publishers import (
    LoggingOutboxPublisher,
    OutboxPublisherConfigurationError,
    RecordingOutboxPublisher,
    SQSOutboxPublisher,
    classify_transport_error,
    get_outbox_publisher,
)


def event_envelope() -> dict:
    return {
        "eventId": "00000000-0000-0000-0000-000000000001",
        "eventType": "application.submitted.v1",
        "schemaVersion": 1,
        "occurredAt": "2026-07-22T00:00:00Z",
        "aggregate": {
            "type": "job_application",
            "id": "42",
            "version": 1,
        },
        "command": {
            "name": "submit",
            "causationId": "00000000-0000-0000-0000-000000000002",
        },
        "correlationId": None,
        "data": {
            "status": "submitted",
            "jobId": "7",
            "candidateUserId": "3",
            "attachedDocumentIds": ["5"],
        },
    }


def expected_sqs_params(envelope: dict) -> dict:
    return {
        "QueueUrl": "https://sqs.us-east-1.amazonaws.com/123456789012/outbox",
        "MessageBody": json.dumps(
            envelope,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "MessageAttributes": {
            "eventId": {
                "DataType": "String",
                "StringValue": envelope["eventId"],
            },
            "eventType": {
                "DataType": "String",
                "StringValue": envelope["eventType"],
            },
            "schemaVersion": {
                "DataType": "String",
                "StringValue": str(envelope["schemaVersion"]),
            },
            "aggregateType": {
                "DataType": "String",
                "StringValue": envelope["aggregate"]["type"],
            },
            "aggregateId": {
                "DataType": "String",
                "StringValue": envelope["aggregate"]["id"],
            },
        },
    }


@pytest.fixture
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_sqs_publisher_sends_canonical_envelope_with_attributes():
    envelope = event_envelope()
    client = boto3.client(
        "sqs",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    publisher = SQSOutboxPublisher(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/outbox",
        region_name="us-east-1",
        timeout_seconds=1,
        client=client,
    )
    stubber = Stubber(client)
    stubber.add_response(
        "send_message",
        {"MessageId": "message-1"},
        expected_sqs_params(envelope),
    )

    with stubber:
        result = publisher.publish(envelope)

    assert result.accepted is True
    assert result.detail == "message-1"


def test_sqs_publisher_classifies_throttling_as_retryable():
    envelope = event_envelope()
    client = boto3.client(
        "sqs",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    publisher = SQSOutboxPublisher(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789012/outbox",
        region_name="us-east-1",
        timeout_seconds=1,
        client=client,
    )
    stubber = Stubber(client)
    stubber.add_client_error(
        "send_message",
        service_error_code="ThrottlingException",
        service_message="too many requests",
        http_status_code=429,
        expected_params=expected_sqs_params(envelope),
    )

    with stubber:
        result = publisher.publish(envelope)

    assert result.accepted is False
    assert result.retryable is True
    assert result.error_category == "throttled"


def test_transport_error_classification_marks_authz_and_invalid_event_non_retryable():
    access_denied = ClientError(
        {
            "Error": {"Code": "InvalidAddress", "Message": "bad queue url"},
            "ResponseMetadata": {"HTTPStatusCode": 400},
        },
        "SendMessage",
    )

    failure = classify_transport_error(access_denied)

    assert failure.retryable is False
    assert failure.error_category == "configuration_error"


def test_get_outbox_publisher_allows_local_logging(monkeypatch, clear_settings_cache):
    monkeypatch.setenv("APP_ENV", "local-kubernetes")
    monkeypatch.setenv("OUTBOX_PUBLISHER", "logging")
    get_settings.cache_clear()

    publisher = get_outbox_publisher()

    assert isinstance(publisher, LoggingOutboxPublisher)


def test_get_outbox_publisher_allows_recording_only_for_tests(monkeypatch, clear_settings_cache):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OUTBOX_PUBLISHER", "recording")
    get_settings.cache_clear()

    publisher = get_outbox_publisher()

    assert isinstance(publisher, RecordingOutboxPublisher)

    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    with pytest.raises(OutboxPublisherConfigurationError):
        get_outbox_publisher("recording")


def test_get_outbox_publisher_requires_sqs_config_in_production(monkeypatch, clear_settings_cache):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OUTBOX_PUBLISHER", "sqs")
    monkeypatch.delenv("OUTBOX_QUEUE_URL", raising=False)
    get_settings.cache_clear()

    with pytest.raises(OutboxPublisherConfigurationError):
        get_outbox_publisher()

    monkeypatch.setenv(
        "OUTBOX_QUEUE_URL",
        "https://sqs.us-east-1.amazonaws.com/123456789012/outbox",
    )
    get_settings.cache_clear()
    assert isinstance(get_outbox_publisher(), SQSOutboxPublisher)


def test_get_outbox_publisher_rejects_logging_and_unknown_publishers_in_production(
    monkeypatch,
    clear_settings_cache,
):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OUTBOX_PUBLISHER", "logging")
    get_settings.cache_clear()
    with pytest.raises(OutboxPublisherConfigurationError):
        get_outbox_publisher()

    monkeypatch.setenv("OUTBOX_PUBLISHER", "kafka")
    get_settings.cache_clear()
    with pytest.raises(OutboxPublisherConfigurationError):
        get_outbox_publisher()
