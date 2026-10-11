"""OPU-60/62 failure injection; no external models, GitHub or cluster required."""

import asyncio
import dataclasses
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from pydantic import ValidationError

from agents.code import main as code_main
from agents.code.agent import CodeAgent, CodeClientError, CodeConfig
from agents.infra import main as infra_main
from agents.infra.agent import InfraClientError
from orchestrator.graph import build_orchestrator_graph, call_agent
from orchestrator.router import AGENT_REGISTRY
from shared.agent_bus import (
    REPLY_TOPIC,
    AgentBusUnavailable,
    AgentWorker,
    KafkaAgentBus,
    request_topic,
)
from shared.kafka_client import (
    KafkaConsumer,
    _deserialize_or_none,
    deserialize_message,
    serialize_message,
)
from shared.models import AgentQuery, KafkaAgentReply
from tests.test_agent_bus import FakeBroker, agent_app, wait_until
from tests.test_agent_failures import infra_agent


@pytest.mark.parametrize("raw", [b"null", b"[]", b"1", b'"text"', b"{bad", b"\xff", b'{"x":NaN}', b'{"x":Infinity}'])
def test_poison_wire_messages_are_dropped(raw):
    assert _deserialize_or_none(raw) is None
    assert _deserialize_or_none(b'{"answer":"valid"}') == {"answer": "valid"}


@pytest.mark.parametrize("payload", [[], None, {"x": float("nan")}, {"x": float("inf")}, {"x": object()}])
def test_unserializable_or_non_json_payloads_are_rejected(payload):
    with pytest.raises((ValueError, TypeError)):
        serialize_message(payload)


def test_consumer_survives_a_handler_exception(caplog):
    stop = threading.Event()
    consumer = KafkaConsumer.__new__(KafkaConsumer)
    consumer.topic = "test-topic"
    consumer._consumer = Mock()
    consumer._consumer.poll.return_value = {0: [SimpleNamespace(value={"bad": True}), SimpleNamespace(value={"good": True})]}
    received = []

    def handler(message):
        if "bad" in message:
            raise ValueError("sensitive-payload")
        received.append(message)
        stop.set()

    consumer.listen(handler, stop=stop)
    assert received == [{"good": True}]
    assert "ValueError" in caplog.text
    assert "sensitive-payload" not in caplog.text


def envelope(**changes):
    return {"correlation_id": "c1", "agent": "infra", "query": {"question": "pods?", "request_id": "r1"},
            "reply_topic": REPLY_TOPIC, "deadline": time.time() + 60, **changes}


@pytest.mark.parametrize("changes", [{"correlation_id": ""}, {"deadline": float("nan")}, {"deadline": float("inf")},
                                    {"deadline": 0}, {"reply_topic": ""}, {"reply_topic": "bad topic"},
                                    {"agent": "unknown"}, {"query": {"question": ""}}])
def test_invalid_envelopes_never_reach_the_agent(changes):
    worker = AgentWorker(agent_app({"answer": "ok"}), "infra")
    with patch.object(worker, "_call_query") as invoke:
        assert worker.handle(envelope(**changes)) is None
    invoke.assert_not_called()
    worker.stop()


@pytest.mark.parametrize("status", [0, 99, 600, "200", True])
def test_reply_requires_a_real_http_status(status):
    with pytest.raises(ValidationError):
        KafkaAgentReply(correlation_id="c1", agent="infra", status_code=status)


def test_worker_returns_safe_failure_for_unserializable_answer(caplog):
    worker = AgentWorker(agent_app(), "infra")
    with patch.object(worker, "_call_query", return_value=(200, {"secret": object()})):
        reply = worker.handle(envelope())
    assert reply.status_code == 500
    assert deserialize_message(serialize_message(reply))["body"] == {
        "detail": "Agent failed to produce a serializable response."}
    assert "secret" not in caplog.text
    worker.stop()


def test_worker_failure_does_not_prevent_next_request():
    worker = AgentWorker(agent_app(), "infra")
    with patch.object(worker, "_call_query", side_effect=[RuntimeError("bug"), (200, {"answer": "recovered"})]):
        assert worker.handle(envelope()).status_code == 500
        assert worker.handle(envelope(correlation_id="c2")).body == {"answer": "recovered"}
    worker.stop()


async def wait_pending(bus):
    async with asyncio.timeout(2):
        while not bus._pending:
            await asyncio.sleep(0.001)
    return next(iter(bus._pending))


def ready_bus():
    bus = KafkaAgentBus()
    bus._producer = Mock()
    bus._ready.set()
    return bus


def test_wrong_agent_and_malformed_reply_cannot_steal_request():
    async def check():
        bus = ready_bus()
        task = asyncio.create_task(bus.request("infra", AgentQuery(question="pods?", request_id="r"), 2))
        correlation = await wait_pending(bus)
        bus._on_reply({"correlation_id": correlation, "agent": "code", "status_code": 200})
        bus._on_reply({"correlation_id": correlation, "agent": "infra", "status_code": 999})
        await asyncio.sleep(0)
        assert not task.done() and correlation in bus._pending
        bus._on_reply({"correlation_id": correlation, "agent": "infra", "status_code": 200, "body": {"answer": "right agent"}})
        assert (await task).body == {"answer": "right agent"}
        assert not bus._pending
        bus.stop()

    asyncio.run(check())


def test_stop_fails_pending_requests_promptly():
    async def check():
        bus = ready_bus()
        task = asyncio.create_task(bus.request("infra", AgentQuery(question="pods?", request_id="r"), 60))
        await wait_pending(bus)
        bus.stop()
        with pytest.raises(AgentBusUnavailable):
            await asyncio.wait_for(task, 0.5)
        assert not bus._pending
        with pytest.raises(AgentBusUnavailable):
            await bus.request("infra", AgentQuery(question="pods?", request_id="r2"), 60)

    asyncio.run(check())


def test_reply_consumer_failure_releases_inflight_requests():
    fail = threading.Event()

    class BrokenConsumer:
        def listen(self, handler, stop=None, on_ready=None):
            on_ready()
            fail.wait(2)
            raise ConnectionError("injected consumer outage")

        def close(self):
            pass

    async def check():
        bus = KafkaAgentBus(producer_factory=Mock, consumer_factory=lambda *args: BrokenConsumer())
        bus.start()
        try:
            task = asyncio.create_task(bus.request("infra", AgentQuery(question="pods?", request_id="r"), 60))
            await wait_pending(bus)
            fail.set()
            with pytest.raises(AgentBusUnavailable):
                await asyncio.wait_for(task, 1)
            assert not bus._ready.is_set() and not bus._pending
        finally:
            fail.set()
            bus.stop()

    asyncio.run(check())


def test_request_cancellation_cleans_up_and_ignores_late_reply():
    async def check():
        bus = ready_bus()
        task = asyncio.create_task(bus.request("infra", AgentQuery(question="pods?", request_id="r"), 60))
        correlation = await wait_pending(bus)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not bus._pending
        bus._on_reply({"correlation_id": correlation, "agent": "infra", "status_code": 200})
        bus.stop()

    asyncio.run(check())


def test_closed_request_loop_does_not_crash_reply_consumer():
    bus = ready_bus()
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    bus._pending["c1"] = (loop, future, "infra")
    loop.close()
    bus._on_reply({"correlation_id": "c1", "agent": "infra", "status_code": 200})
    assert not bus._pending
    bus.stop()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_timeout_never_publishes(timeout):
    bus = ready_bus()
    with pytest.raises(ValueError):
        asyncio.run(bus.request("infra", AgentQuery(question="pods?", request_id="r"), timeout))
    bus._producer.send.assert_not_called()
    bus.stop()


def test_http_agent_has_wall_clock_deadline_and_is_not_retried():
    cancelled = []
    calls = []

    async def slow(request):
        calls.append(request)
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)

    spec = dataclasses.replace(AGENT_REGISTRY["infra"], timeout_s=0.02)
    with patch.dict(AGENT_REGISTRY, {"infra": spec}):
        result = asyncio.run(call_agent("infra", AgentQuery(question="pods?", request_id="r"), httpx.MockTransport(slow)))
    assert result.status == "timeout" and result.error.code == "timeout"
    assert len(calls) == 1 and cancelled == [True]


def test_four_kafka_branches_keep_success_through_bad_reply_timeout_and_failure():
    broker = FakeBroker()
    bus = KafkaAgentBus(producer_factory=broker.producer, consumer_factory=broker.consumer)
    workers = []
    try:
        bus.start()
        for name, app in [("rag", agent_app({"answer": "Runbook evidence [runbook.md]", "sources": ["runbook.md"]})),
                          ("monitoring", agent_app({"sources": []})), ("code", agent_app(status=500))]:
            worker = AgentWorker(app, name, producer_factory=broker.producer, consumer_factory=broker.consumer)
            workers.append(worker)
            worker.start()
            wait_until(lambda name=name: broker.subscribers[request_topic(name)])
        spec = dataclasses.replace(AGENT_REGISTRY["infra"], timeout_s=0.05)
        with patch.dict(AGENT_REGISTRY, {"infra": spec}):
            graph = build_orchestrator_graph(bus=bus)
            out = asyncio.run(graph.ainvoke({"question": "runbook alert kubernetes PR", "request_id": "r", "results": []}))

        outcomes = {result.agent: result for result in out["results"]}
        assert out["status"] == "partial" and out["sources"] == ["runbook.md"]
        assert outcomes["monitoring"].error.code == "invalid_response"
        assert outcomes["infra"].error.code == "timeout"
        assert outcomes["code"].error.code == "agent_error"
        assert "[runbook.md]" in out["final_answer"] and "Unavailable:" in out["final_answer"]
        assert not bus._pending
    finally:
        bus.stop()
        for worker in workers:
            worker.stop()


@pytest.mark.parametrize("name,status,code,retries", [("infra", 503, "unavailable", 2), ("infra", 500, "agent_error", 1),
                                                    ("code", 503, "unavailable", 2), ("code", 404, "bad_request", 1)])
def test_real_infra_code_handlers_report_failures_over_kafka(name, status, code, retries):
    broker = FakeBroker()
    bus = KafkaAgentBus(producer_factory=broker.producer, consumer_factory=broker.consumer)
    app = infra_main.app if name == "infra" else code_main.app
    module = infra_main if name == "infra" else code_main
    agent = infra_agent() if name == "infra" else CodeAgent(CodeConfig(github_repo="acme/app"))
    method = "list_nodes" if name == "infra" else "list_commits"
    failure = InfraClientError("backend test failure", status_code=status) if name == "infra" else CodeClientError("backend test failure", status_code=status)
    worker = AgentWorker(app, name, producer_factory=broker.producer, consumer_factory=broker.consumer)
    try:
        with patch.object(module, "get_agent", return_value=agent), patch.object(agent, method, side_effect=failure) as backend:
            bus.start()
            worker.start()
            wait_until(lambda: broker.subscribers[request_topic(name)])
            question = "list k8s nodes" if name == "infra" else "show commits"
            result = asyncio.run(call_agent(name, AgentQuery(question=question, request_id="r"), bus=bus))
            assert result.status == "error" and result.error.code == code
            assert backend.call_count == retries
    finally:
        bus.stop()
        worker.stop()


def test_serialization_failure_is_safe_and_retry_bounded():
    bus = ready_bus()
    bus._producer.send.side_effect = TypeError("sensitive payload")
    result = asyncio.run(call_agent("infra", AgentQuery(question="pods?", request_id="r"), bus=bus))
    assert result.error.code == "unavailable"
    assert bus._producer.send.call_count == 2
    assert "sensitive payload" not in json.dumps(result.model_dump())
    assert not bus._pending
    bus.stop()
