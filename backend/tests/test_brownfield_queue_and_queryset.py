# ruff: noqa: INP001
"""Tests for queue operations and queryset wrapper."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.services.queue import QueuedTask, _coerce_datetime, _decode_task, _requeue_with_attempt
from app.services.webhooks.queue import (
    QueuedInboundDelivery,
    TASK_TYPE,
    _task_from_payload,
    decode_webhook_task,
)


# --- Queue tests ---


def test_queued_task_to_json_roundtrip() -> None:
    """QueuedTask serializes to JSON and can be decoded back."""
    now = datetime.now(UTC)
    task = QueuedTask(task_type="test", payload={"key": "value"}, created_at=now, attempts=2)
    json_str = task.to_json()
    parsed = json.loads(json_str)
    assert parsed["task_type"] == "test"
    assert parsed["payload"] == {"key": "value"}
    assert parsed["attempts"] == 2


def test_decode_task_standard_format() -> None:
    """_decode_task parses standard task format."""
    now = datetime.now(UTC)
    raw = json.dumps({
        "task_type": "test",
        "payload": {"foo": "bar"},
        "created_at": now.isoformat(),
        "attempts": 1,
    })
    task = _decode_task(raw, "test-queue")
    assert task.task_type == "test"
    assert task.payload == {"foo": "bar"}
    assert task.attempts == 1


def test_decode_task_legacy_format() -> None:
    """_decode_task handles legacy payloads without task_type field."""
    raw = json.dumps({
        "board_id": str(uuid4()),
        "webhook_id": str(uuid4()),
        "payload_id": str(uuid4()),
        "received_at": datetime.now(UTC).isoformat(),
        "attempts": 0,
    })
    task = _decode_task(raw, "test-queue")
    assert task.task_type == "legacy"


def test_decode_task_bytes_input() -> None:
    """_decode_task handles bytes input."""
    raw = json.dumps({
        "task_type": "test",
        "payload": {},
        "created_at": datetime.now(UTC).isoformat(),
    }).encode("utf-8")
    task = _decode_task(raw, "test-queue")
    assert task.task_type == "test"


def test_requeue_with_attempt_increments() -> None:
    """_requeue_with_attempt increments attempt counter."""
    task = QueuedTask(task_type="test", payload={}, created_at=datetime.now(UTC), attempts=0)
    requeued = _requeue_with_attempt(task)
    assert requeued.attempts == 1
    assert requeued.task_type == task.task_type


def test_coerce_datetime_string() -> None:
    """_coerce_datetime parses ISO strings."""
    now = datetime.now(UTC)
    result = _coerce_datetime(now.isoformat())
    assert result.year == now.year


def test_coerce_datetime_none() -> None:
    """_coerce_datetime returns now() for None."""
    result = _coerce_datetime(None)
    assert isinstance(result, datetime)


def test_coerce_datetime_numeric() -> None:
    """_coerce_datetime handles unix timestamps."""
    import time

    ts = time.time()
    result = _coerce_datetime(ts)
    assert isinstance(result, datetime)


# --- Webhook queue tests ---


def test_task_from_payload_creates_correct_type() -> None:
    """_task_from_payload creates QueuedTask with correct type."""
    delivery = QueuedInboundDelivery(
        board_id=uuid4(),
        webhook_id=uuid4(),
        payload_id=uuid4(),
        received_at=datetime.now(UTC),
        attempts=1,
    )
    task = _task_from_payload(delivery)
    assert task.task_type == TASK_TYPE
    assert task.attempts == 1
    assert "board_id" in task.payload


def test_decode_webhook_task_roundtrip() -> None:
    """encode -> decode roundtrip for webhook tasks."""
    delivery = QueuedInboundDelivery(
        board_id=uuid4(),
        webhook_id=uuid4(),
        payload_id=uuid4(),
        received_at=datetime.now(UTC),
        attempts=3,
    )
    task = _task_from_payload(delivery)
    decoded = decode_webhook_task(task)
    assert decoded.board_id == delivery.board_id
    assert decoded.webhook_id == delivery.webhook_id
    assert decoded.payload_id == delivery.payload_id


def test_decode_webhook_task_rejects_wrong_type() -> None:
    """decode_webhook_task raises on unexpected task_type."""
    task = QueuedTask(task_type="unknown", payload={}, created_at=datetime.now(UTC))
    with pytest.raises(ValueError, match="Unexpected task_type"):
        decode_webhook_task(task)


# --- QuerySet tests ---


def test_queryset_immutable_chaining() -> None:
    """QuerySet methods return new instances (immutable)."""
    from app.db.queryset import qs
    from app.models.agents import Agent

    base = qs(Agent)
    filtered = base.filter_by(name="test")
    assert base is not filtered
    limited = filtered.limit(10)
    assert filtered is not limited
    with_offset = limited.offset(5)
    assert limited is not with_offset
