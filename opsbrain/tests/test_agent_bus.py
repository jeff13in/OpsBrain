"""Tests for the Kafka request/reply layer between the Orchestrator and agents (OPU-50).

Kafka is replaced by an in-memory broker that still pushes every message through
the real serialize/deserialize functions, so the wire format is exercised. The
agents are small FastAPI apps answering /query the way the real ones do. Running
against a live broker in docker compose is OPU-51.
"""

from __future__ import annotations

import asyncio
import dataclasses
import queue
import threading
import time
import unittest
from collections import defaultdict
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from orchestrator.graph import build_orchestrator_graph, call_agent
from orchestrator.router import AGENT_REGISTRY
from shared import agent_bus
from shared.agent_bus import (
    REPLY_TOPIC,
    AgentBusUnavailable,
    AgentWorker,
    KafkaAgentBus,
    attach_kafka_worker,
    request_topic,
)
from shared.kafka_client import (
    _deserialize_or_none,
    deserialize_message,
    serialize_message,
)
from shared.models import AgentQuery, KafkaAgentReply, KafkaAgentRequest


class FakeBroker:
    """Topics fan out to every subscribed consumer, like separate consumer groups."""

    def __init__(self) -> None:
        self.subscribers: dict[str, list[queue.Queue]] = defaultdict(list)
        self.sent: list[tuple[str, dict]] = []
        self.fail_sends = False
        self.lock = threading.Lock()

    def producer(self) -> FakeProducer:
        return FakeProducer(self)

    def consumer(self, topic: str, group_id: str, auto_offset_reset: str) -> FakeConsumer:
        q: queue.Queue = queue.Queue()
        with self.lock:
            self.subscribers[topic].append(q)
        return FakeConsumer(q)

    def publish(self, topic: str, message) -> None:
        if self.fail_sends:
            raise ConnectionError("broker down")
        wire = deserialize_message(serialize_message(message))
        with self.lock:
            self.sent.append((topic, wire))
            targets = list(self.subscribers[topic])
        for q in targets:
            q.put(wire)

    def sent_to(self, topic: str) -> list[dict]:
        return [m for t, m in self.sent if t == topic]


class FakeProducer:
    def __init__(self, broker: FakeBroker) -> None:
        self.broker = broker

    def send(self, topic: str, message) -> None:
        self.broker.publish(topic, message)

    def close(self) -> None:
        pass


class FakeConsumer:
    def __init__(self, q: queue.Queue) -> None:
        self.q = q

    def listen(self, handler, stop=None, on_ready=None) -> None:
        if on_ready:
            on_ready()
        while stop is None or not stop.is_set():
            try:
                handler(self.q.get(timeout=0.02))
            except queue.Empty:
                continue

    def close(self) -> None:
        pass


def agent_app(reply=None, *, status: int = 200, calls: list | None = None) -> FastAPI:
    """A fake agent whose /query returns `reply` (dict, or str for a non-JSON body) or raises HTTP `status`."""
    app = FastAPI()

    @app.post("/query")
    def query(body: dict):
        if calls is not None:
            calls.append(body)
        if status != 200:
            raise HTTPException(status_code=status, detail="backend down")
        if isinstance(reply, str):
            return PlainTextResponse(reply)
        return reply

    return app


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met in time")


class KafkaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = FakeBroker()
        self.workers: list[AgentWorker] = []
        self.bus = KafkaAgentBus(producer_factory=self.broker.producer, consumer_factory=self.broker.consumer)
        self.bus.start()
        self.addCleanup(self.bus.stop)

    def start_worker(self, agent: str, app: FastAPI) -> AgentWorker:
        worker = AgentWorker(app, agent, producer_factory=self.broker.producer, consumer_factory=self.broker.consumer)
        worker.start()
        self.addCleanup(worker.stop)
        wait_until(lambda: self.broker.subscribers[request_topic(agent)])
        return worker

    def call(self, agent: str, question: str = "what is broken right now?"):
        return asyncio.run(call_agent(agent, AgentQuery(question=question, request_id="r1"), bus=self.bus))


class RoundTripTests(KafkaTestCase):
    def test_request_reaches_the_agent_and_its_reply_comes_back(self) -> None:
        calls: list = []
        self.start_worker("infra", agent_app({"answer": "3 pods", "sources": ["k8s"], "data": {"n": 3}}, calls=calls))

        result = self.call("infra", "how many pods?")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.answer, "3 pods")
        self.assertEqual(result.sources, ["k8s"])
        self.assertEqual(result.data, {"n": 3})
        # The agent got exactly the AgentQuery the HTTP path would POST.
        self.assertEqual(calls, [{"question": "how many pods?", "request_id": "r1"}])

    def test_messages_on_the_wire_match_the_shared_models(self) -> None:
        self.start_worker("code", agent_app({"answer": "ok"}))

        self.call("code")

        request = KafkaAgentRequest.model_validate(self.broker.sent_to(request_topic("code"))[0])
        reply = KafkaAgentReply.model_validate(self.broker.sent_to(REPLY_TOPIC)[0])
        self.assertEqual(request.reply_topic, REPLY_TOPIC)
        self.assertEqual(reply.correlation_id, request.correlation_id)
        self.assertEqual((reply.agent, reply.status_code), ("code", 200))

    def test_extra_reply_fields_are_kept_in_data(self) -> None:
        self.start_worker("rag", agent_app({"answer": "restart it", "sources": ["runbook.md"], "grounded": True}))

        result = self.call("rag")

        self.assertEqual(result.data, {"grounded": True})

    def test_graph_fans_out_over_kafka_and_merges_results(self) -> None:
        self.start_worker("monitoring", agent_app({"answer": "2 alerts firing", "sources": ["alertmanager"]}))
        self.start_worker("infra", agent_app({"answer": "1 pod crashlooping", "sources": ["k8s"]}))
        graph = build_orchestrator_graph(bus=self.bus)

        out = asyncio.run(graph.ainvoke({"request_id": "r1", "question": "which alert is firing for the pod?", "history": [], "results": []}))

        self.assertEqual(out["routing"].agents, ["monitoring", "infra"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(sorted(r.agent for r in out["results"]), ["infra", "monitoring"])
        self.assertEqual(out["sources"], ["alertmanager", "k8s"])


class FailureTests(KafkaTestCase):
    def test_503_is_retried_once_then_reported_unavailable(self) -> None:
        calls: list = []
        self.start_worker("monitoring", agent_app(status=503, calls=calls))

        result = self.call("monitoring")

        self.assertEqual(len(calls), 2)
        self.assertEqual((result.status, result.error.code, result.error.retryable), ("error", "unavailable", True))
        self.assertIn("backend down", result.error.message)

    def test_4xx_is_bad_request_and_not_retried(self) -> None:
        calls: list = []
        self.start_worker("code", agent_app(status=404, calls=calls))

        result = self.call("code")

        self.assertEqual(len(calls), 1)
        self.assertEqual(result.error.code, "bad_request")

    def test_agent_crash_is_agent_error(self) -> None:
        app = FastAPI()

        @app.post("/query")
        def query(body: dict):
            raise RuntimeError("bug")

        self.start_worker("infra", app)

        result = self.call("infra")

        self.assertEqual(result.error.code, "agent_error")

    def test_non_json_2xx_is_invalid_response(self) -> None:
        self.start_worker("code", agent_app("not json"))

        self.assertEqual(self.call("code").error.code, "invalid_response")

    def test_unresponsive_agent_times_out_without_retry(self) -> None:
        fast = dataclasses.replace(AGENT_REGISTRY["infra"], timeout_s=0.2)
        with patch.dict(AGENT_REGISTRY, {"infra": fast}):
            result = self.call("infra")  # no worker running for infra

        self.assertEqual((result.status, result.error.code), ("timeout", "timeout"))
        self.assertEqual(len(self.broker.sent_to(request_topic("infra"))), 1)

    def test_broker_rejecting_the_send_is_unavailable_after_one_retry(self) -> None:
        wait_until(self.bus._ready.is_set)
        self.broker.fail_sends = True

        result = self.call("rag")

        self.assertEqual((result.status, result.error.code), ("error", "unavailable"))

    def test_bus_that_never_connected_is_unavailable(self) -> None:
        def no_broker():
            raise ConnectionError("no brokers")

        bus = KafkaAgentBus(producer_factory=no_broker, consumer_factory=self.broker.consumer, ready_timeout_s=0.1)
        bus.start()
        self.addCleanup(bus.stop)

        with self.assertRaises(AgentBusUnavailable):
            asyncio.run(bus.request("rag", AgentQuery(question="hi there", request_id="r"), timeout_s=5))

    def test_one_failing_agent_gives_a_partial_answer(self) -> None:
        self.start_worker("monitoring", agent_app({"answer": "2 alerts firing"}))
        self.start_worker("infra", agent_app(status=500))
        graph = build_orchestrator_graph(bus=self.bus)

        out = asyncio.run(graph.ainvoke({"request_id": "r1", "question": "which alert is firing for the pod?", "history": [], "results": []}))

        self.assertEqual(out["status"], "partial")
        self.assertIn("Unavailable: infra (agent_error)", out["final_answer"])


class WorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list = []
        self.worker = AgentWorker(agent_app({"answer": "x"}, calls=self.calls), "infra", clock=lambda: 1000.0)

    def request(self, **overrides) -> dict:
        message = KafkaAgentRequest(
            correlation_id="c1", agent="infra", query=AgentQuery(question="pods?", request_id="r1"),
            reply_topic=REPLY_TOPIC, deadline=2000.0,
        ).model_dump()
        return {**message, **overrides}

    def test_answers_a_valid_request(self) -> None:
        reply = self.worker.handle(self.request())

        self.assertEqual((reply.correlation_id, reply.status_code, reply.body), ("c1", 200, {"answer": "x"}))

    def test_skips_requests_the_orchestrator_already_gave_up_on(self) -> None:
        self.assertIsNone(self.worker.handle(self.request(deadline=999.0)))
        self.assertEqual(self.calls, [])

    def test_drops_malformed_and_misrouted_requests(self) -> None:
        self.assertIsNone(self.worker.handle({"question": "no envelope"}))
        self.assertIsNone(self.worker.handle(self.request(agent="code")))
        self.assertEqual(self.calls, [])

    def test_agent_side_validation_errors_come_back_as_4xx(self) -> None:
        class RagQuery(BaseModel):  # RAG's /query wants at least 5 characters
            question: str = Field(min_length=5)

        app = FastAPI()

        @app.post("/query")
        def query(body: RagQuery):
            return {"answer": "x"}

        reply = AgentWorker(app, "rag", clock=lambda: 1000.0).handle(self.request(agent="rag", query={"question": "hi", "request_id": "r1"}))

        self.assertEqual(reply.status_code, 422)


class BusTests(unittest.TestCase):
    def test_ignores_malformed_and_unknown_replies(self) -> None:
        bus = KafkaAgentBus()
        bus._on_reply({"not": "a reply"})
        bus._on_reply({"correlation_id": "someone-elses", "agent": "rag", "status_code": 200, "body": {}})
        self.assertEqual(bus._pending, {})


class AttachTests(unittest.TestCase):
    def test_no_worker_over_http(self) -> None:
        with patch.dict("os.environ", {"AGENT_TRANSPORT": "http"}):
            self.assertIsNone(attach_kafka_worker(FastAPI(), "rag"))

    def test_worker_runs_for_the_app_lifespan_over_kafka(self) -> None:
        app = agent_app({"answer": "x"})
        with patch.dict("os.environ", {"AGENT_TRANSPORT": "kafka"}), \
             patch.object(agent_bus.AgentWorker, "start") as start, \
             patch.object(agent_bus.AgentWorker, "stop") as stop:
            worker = attach_kafka_worker(app, "rag")
            with TestClient(app) as client:
                start.assert_called_once()
                self.assertEqual(client.post("/query", json={}).status_code, 200)  # HTTP still works
            stop.assert_called_once()
        self.assertEqual(worker.agent, "rag")


class SerializationTests(unittest.TestCase):
    def test_consumer_drops_non_json_instead_of_raising(self) -> None:
        self.assertIsNone(_deserialize_or_none(b"\xff not json"))
        self.assertEqual(_deserialize_or_none(b'{"a": 1}'), {"a": 1})


class ModelPreservationTests(KafkaTestCase):
    def test_kafka_keeps_separate_router_synthesis_and_metrics(self):
        from shared.observability import AGENT_EXECUTIONS
        from tests.test_orchestrator_graph import FakeLLM

        self.start_worker("rag", agent_app({"answer": "Follow runbook", "sources": ["runbook.md"]}))
        self.start_worker("monitoring", agent_app({"answer": "No alerts", "sources": ["alertmanager:alerts"]}))
        router = FakeLLM('{"agents":["rag","monitoring"]}')
        synth = FakeLLM("", "Combined [runbook.md] [alertmanager:alerts]")
        before = AGENT_EXECUTIONS.labels("rag", "ok")._value.get()
        graph = build_orchestrator_graph(llm=router, synth_llm=synth, bus=self.bus)
        out = asyncio.run(graph.ainvoke({"request_id": "r", "question": "Any alerts?", "history": [], "results": []}))
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["final_answer"], "Combined [runbook.md] [alertmanager:alerts]")
        self.assertEqual(len(router.prompts), 1)
        self.assertEqual(len(synth.prompts), 1)
        self.assertEqual(AGENT_EXECUTIONS.labels("rag", "ok")._value.get(), before + 1)

    def test_slow_publish_is_bounded_by_request_deadline(self):
        wait_until(self.bus._ready.is_set)

        def slow_send(*args):
            time.sleep(0.1)

        async def check():
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                await self.bus.request("rag", AgentQuery(question="hello", request_id="r"), 0.01)
            self.assertLess(time.monotonic() - started, 0.08)
            self.assertEqual(self.bus._pending, {})

        with patch.object(self.bus._producer, "send", side_effect=slow_send):
            asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
