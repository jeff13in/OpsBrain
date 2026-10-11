"""Kafka producer / consumer wrappers for async agent communication.

Every agent and the Orchestrator import from here rather than talking to
kafka-python directly, so serialization stays consistent no matter which
service is sending or receiving.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from kafka import KafkaConsumer as _KafkaConsumer
from kafka import KafkaProducer as _KafkaProducer
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def serialize_message(message: BaseModel | dict[str, Any]) -> bytes:
    """Turn a Pydantic model or plain dict into the bytes that go on the wire."""
    if isinstance(message, BaseModel):
        return message.model_dump_json().encode("utf-8")
    return json.dumps(message).encode("utf-8")


def deserialize_message(raw: bytes) -> dict[str, Any]:
    """Turn wire bytes back into a plain dict (callers validate into a model if needed)."""
    return json.loads(raw.decode("utf-8"))


def _deserialize_or_none(raw: bytes) -> dict[str, Any] | None:
    """Consumer-side deserializer: a malformed message becomes None instead of
    raising inside poll(), which would stop the consumer on that offset for good."""
    try:
        return deserialize_message(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Dropping a Kafka message that isn't UTF-8 JSON.")
        return None


class KafkaProducer:
    """Publish messages (Pydantic models or plain dicts) to a Kafka topic."""

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        self._producer = _KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=serialize_message,
        )

    def send(self, topic: str, message: BaseModel | dict[str, Any]) -> None:
        """Publish to a topic and block until the broker acknowledges it."""
        future = self._producer.send(topic, value=message)
        future.get(timeout=10)

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()


class KafkaConsumer:
    """Consume messages from a Kafka topic and hand each one to a handler as a dict."""

    def __init__(
        self,
        topic: str,
        bootstrap_servers: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
    ) -> None:
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self._consumer = _KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            value_deserializer=_deserialize_or_none,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=True,
        )

    def listen(
        self,
        handler: Callable[[dict[str, Any]], None],
        stop: threading.Event | None = None,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        """Block, calling handler(message_dict) for each incoming message.

        Returns once `stop` is set (checked at least every 0.5s). `on_ready` is
        called once, as soon as partitions are assigned — messages published
        before that may not be seen by a consumer that starts at "latest".
        """
        ready = on_ready is None
        while stop is None or not stop.is_set():
            batches = self._consumer.poll(timeout_ms=500)
            if not ready and self._consumer.assignment():
                ready = True
                on_ready()
            for records in batches.values():
                for record in records:
                    if record.value is not None:
                        handler(record.value)

    def close(self) -> None:
        self._consumer.close()
