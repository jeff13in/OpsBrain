"""Request/reply between the Orchestrator and the agents over Kafka (OPU-50).

  Orchestrator ── KafkaAgentRequest ──▶ opsbrain.agent.<agent>.requests ──▶ AgentWorker
       ▲                                                                       │
       └──── KafkaAgentReply ◀── opsbrain.agent.replies ◀── agent's own /query ┘

* AgentWorker runs inside each agent. It consumes the agent's request topic and
  answers each request by calling the agent's own /query in-process, so request
  validation and the status codes are exactly what the HTTP path returns.
* KafkaAgentBus runs inside the Orchestrator. It publishes requests and matches
  replies back to the waiting call by correlation_id. Each Orchestrator process
  reads the reply topic in its own consumer group, so with several replicas every
  one sees every reply and keeps only its own.

Both are enabled with AGENT_TRANSPORT=kafka (HTTP otherwise) and connect to
KAFKA_BOOTSTRAP_SERVERS. kafka-python is imported only when a real connection is
made, so agents without it installed still run over HTTP.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Protocol

from pydantic import ValidationError

from shared.models import AgentQuery, KafkaAgentReply, KafkaAgentRequest

logger = logging.getLogger(__name__)

REPLY_TOPIC = "opsbrain.agent.replies"


def request_topic(agent: str) -> str:
    return f"opsbrain.agent.{agent}.requests"


def kafka_enabled() -> bool:
    return os.getenv("AGENT_TRANSPORT", "http").strip().lower() == "kafka"


def bootstrap_servers() -> str:
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


class AgentBusUnavailable(Exception):
    """Kafka couldn't take the request (broker down, not connected yet). Retryable."""


# ── Pluggable connections (real Kafka by default, in-memory fakes in tests) ──────

class Producer(Protocol):
    def send(self, topic: str, message: Any) -> None: ...
    def close(self) -> None: ...


class Consumer(Protocol):
    def listen(self, handler: Callable[[dict[str, Any]], None], stop: threading.Event | None = None,
               on_ready: Callable[[], None] | None = None) -> None: ...
    def close(self) -> None: ...


ProducerFactory = Callable[[], Producer]
ConsumerFactory = Callable[[str, str, str], Consumer]   # (topic, group_id, auto_offset_reset)


def _kafka_producer() -> Producer:
    from shared.kafka_client import KafkaProducer
    return KafkaProducer(bootstrap_servers())


def _kafka_consumer(topic: str, group_id: str, auto_offset_reset: str) -> Consumer:
    from shared.kafka_client import KafkaConsumer
    return KafkaConsumer(topic, bootstrap_servers(), group_id, auto_offset_reset=auto_offset_reset)


def _connect(factory: Callable[[], Any], stop: threading.Event, what: str) -> Any | None:
    """Retry `factory` with backoff until it succeeds or `stop` is set (→ None).

    Services start before the broker is ready, so failing to connect is normal
    for the first few seconds and must not crash the service.
    """
    delay = 1.0
    while not stop.is_set():
        try:
            return factory()
        except Exception as exc:  # noqa: BLE001 - any connect failure is retried
            logger.warning("Kafka %s not ready (%s); retrying in %.0fs.", what, exc.__class__.__name__, delay)
            stop.wait(delay)
            delay = min(delay * 2, 30.0)
    return None


def _close(conn: Any) -> None:
    try:
        conn.close()
    except Exception:
        logger.debug("Error closing Kafka connection.", exc_info=True)


# ── Agent side ──────────────────────────────────────────────────────────────────

class AgentWorker:
    """Answers one agent's Kafka requests by calling its own /query in-process."""

    def __init__(
        self,
        app: Any,
        agent: str,
        *,
        query_path: str = "/query",
        producer_factory: ProducerFactory = _kafka_producer,
        consumer_factory: ConsumerFactory = _kafka_consumer,
        max_concurrency: int = 4,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.app = app
        self.agent = agent
        self.query_path = query_path
        self._producer_factory = producer_factory
        self._consumer_factory = consumer_factory
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._producer: Producer | None = None
        # Requests are handled concurrently: one slow RAG answer mustn't make
        # every request queued behind it miss its deadline.
        self._pool = ThreadPoolExecutor(max_workers=max_concurrency, thread_name_prefix=f"{agent}-kafka")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=f"{self.agent}-kafka-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _run(self) -> None:
        self._producer = _connect(self._producer_factory, self._stop, "producer")
        consumer = _connect(
            # "earliest": requests published before this worker's first assignment
            # are still picked up; expired ones are dropped by the deadline check.
            lambda: self._consumer_factory(request_topic(self.agent), f"{self.agent}-agent", "earliest"),
            self._stop, "consumer",
        )
        if self._producer is None or consumer is None:
            return
        logger.info("%s agent listening on %s", self.agent, request_topic(self.agent))
        try:
            consumer.listen(lambda raw: self._pool.submit(self.handle, raw), stop=self._stop)
        except Exception:
            logger.exception("%s agent's Kafka consumer stopped unexpectedly.", self.agent)
        finally:
            _close(consumer)
            _close(self._producer)

    def handle(self, raw: dict[str, Any]) -> KafkaAgentReply | None:
        """Answer one request and publish the reply. Returns the reply (None if skipped)."""
        try:
            request = KafkaAgentRequest.model_validate(raw)
        except ValidationError as exc:
            logger.warning("Dropping malformed request on %s: %d error(s).", request_topic(self.agent), exc.error_count())
            return None
        if request.agent != self.agent:
            logger.warning("Dropping request for %r on %s.", request.agent, request_topic(self.agent))
            return None
        if self._clock() >= request.deadline:
            logger.info("Skipping request %s: the Orchestrator already timed out.", request.correlation_id)
            return None

        status_code, body = self._call_query(request.query)
        reply = KafkaAgentReply(correlation_id=request.correlation_id, agent=self.agent, status_code=status_code, body=body)
        if self._producer is None:
            return reply  # not connected (only reachable when handle() is called directly)
        try:
            self._producer.send(request.reply_topic, reply)
        except Exception:
            # The Orchestrator will report this agent as timed out.
            logger.exception("Could not publish reply %s.", request.correlation_id)
        return reply

    def _call_query(self, query: AgentQuery) -> tuple[int, Any]:
        from fastapi.testclient import TestClient

        # In-process ASGI call; no lifespan, no network. raise_server_exceptions=False
        # so a crash in the handler comes back as a 500 like it would over HTTP.
        client = TestClient(self.app, raise_server_exceptions=False)
        try:
            resp = client.post(self.query_path, json=query.model_dump())
        except Exception:
            logger.exception("%s /query raised outside the app.", self.agent)
            return 500, {"detail": "Agent failed to handle the request."}
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text


def attach_kafka_worker(app: Any, agent: str, query_path: str = "/query") -> AgentWorker | None:
    """Run an AgentWorker for the lifetime of `app` when AGENT_TRANSPORT=kafka.

    The agent's HTTP endpoints keep working either way.
    """
    if not kafka_enabled():
        return None
    worker = AgentWorker(app, agent, query_path=query_path)
    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(a: Any):
        worker.start()
        try:
            async with inner(a) as state:
                yield state
        finally:
            worker.stop()

    app.router.lifespan_context = lifespan
    return worker


# ── Orchestrator side ───────────────────────────────────────────────────────────

class KafkaAgentBus:
    """Publishes agent requests and resolves each one with its matching reply."""

    def __init__(
        self,
        *,
        producer_factory: ProducerFactory = _kafka_producer,
        consumer_factory: ConsumerFactory = _kafka_consumer,
        reply_topic: str = REPLY_TOPIC,
        ready_timeout_s: float = 10.0,
    ) -> None:
        self.reply_topic = reply_topic
        # Own group per process: every replica receives every reply.
        self.group_id = f"orchestrator-{uuid.uuid4().hex[:12]}"
        self._producer_factory = producer_factory
        self._consumer_factory = consumer_factory
        self._ready_timeout_s = ready_timeout_s
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._producer: Producer | None = None
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Future]] = {}

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="orchestrator-kafka-replies", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        self._producer = _connect(self._producer_factory, self._stop, "producer")
        # "latest": a new process has no use for replies sent before it started.
        consumer = _connect(lambda: self._consumer_factory(self.reply_topic, self.group_id, "latest"), self._stop, "consumer")
        if self._producer is None or consumer is None:
            return
        try:
            consumer.listen(self._on_reply, stop=self._stop, on_ready=self._ready.set)
        except Exception:
            logger.exception("Orchestrator's Kafka reply consumer stopped unexpectedly.")
        finally:
            self._ready.clear()
            _close(consumer)
            _close(self._producer)

    def _on_reply(self, raw: dict[str, Any]) -> None:
        try:
            reply = KafkaAgentReply.model_validate(raw)
        except ValidationError:
            logger.warning("Dropping malformed reply on %s.", self.reply_topic)
            return
        with self._lock:
            entry = self._pending.pop(reply.correlation_id, None)
        if entry is None:
            return  # another replica's request, or one that already timed out
        loop, future = entry
        loop.call_soon_threadsafe(_resolve, future, reply)

    async def request(self, agent: str, query: AgentQuery, timeout_s: float) -> KafkaAgentReply:
        """Send one request and wait for its reply.

        Raises TimeoutError if no reply arrives within `timeout_s`, and
        AgentBusUnavailable if Kafka can't take the request.
        """
        started = time.monotonic()
        if not self._ready.is_set():
            # Startup: the reply consumer must be assigned before we publish, or
            # a fast reply could arrive before we're listening for it.
            wait = min(self._ready_timeout_s, timeout_s)
            if not await asyncio.to_thread(self._ready.wait, wait):
                raise AgentBusUnavailable("Not connected to Kafka.")
        producer = self._producer
        if producer is None:
            raise AgentBusUnavailable("Not connected to Kafka.")

        remaining = timeout_s - (time.monotonic() - started)
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        correlation_id = uuid.uuid4().hex
        message = KafkaAgentRequest(
            correlation_id=correlation_id,
            agent=agent,
            query=query,
            reply_topic=self.reply_topic,
            deadline=time.time() + remaining,
        )
        with self._lock:
            self._pending[correlation_id] = (loop, future)
        try:
            try:
                await asyncio.to_thread(producer.send, request_topic(agent), message)
            except Exception as exc:
                raise AgentBusUnavailable(f"Kafka did not accept the request: {exc.__class__.__name__}") from exc
            remaining = timeout_s - (time.monotonic() - started)
            return await asyncio.wait_for(future, timeout=max(remaining, 0))
        finally:
            with self._lock:
                self._pending.pop(correlation_id, None)


def _resolve(future: asyncio.Future, reply: KafkaAgentReply) -> None:
    if not future.done():
        future.set_result(reply)


def reply_detail(body: Any) -> str:
    """The error text of a non-2xx reply, matching what the HTTP path reports."""
    if isinstance(body, str):
        return body
    return json.dumps(body) if body is not None else ""
