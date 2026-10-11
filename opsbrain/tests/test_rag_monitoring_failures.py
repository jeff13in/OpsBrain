"""OPU-61: real RAG/Monitoring handlers, with injected dependencies only."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from monitoring import main as monitoring_main
from monitoring.agent import MonitoringClientError
from psycopg import OperationalError
from rag import main as rag_main
from rag.agent import AgentResponse

from orchestrator.graph import build_orchestrator_graph, call_agent
from shared.agent_bus import AgentWorker, KafkaAgentBus, request_topic
from shared.models import AgentQuery
from tests.test_agent_bus import FakeBroker, wait_until
from tests.test_orchestrator_graph import FakeLLM


def valid_reply(name):
    if name == "rag":
        return AgentResponse(answer="Use the runbook [runbook.md]", sources=["runbook.md"], grounded=True, retrieved_chunks=2)
    return {"answer": "No alerts [alertmanager:alerts]", "sources": ["alertmanager:alerts"], "data": {"alerts": {"total": 0}}}


def module_for(name):
    return rag_main if name == "rag" else monitoring_main


@pytest.mark.parametrize("name", ["rag", "monitoring"])
def test_valid_query_preserves_answer_sources_and_metadata(name):
    module = module_for(name)
    agent = Mock(ask=Mock(return_value=valid_reply(name)))
    with patch.object(module, "get_agent", return_value=agent):
        response = TestClient(module.app).post("/query", json={"question": "runbook alerts?", "request_id": "r"})
    assert response.status_code == 200
    body = response.json()
    assert body["sources"] and body["answer"]
    if name == "rag":
        assert body["grounded"] is True and body["retrieved_chunks"] == 2
        assert body["validation_errors"] == []
    else:
        assert body["data"] == {"alerts": {"total": 0}}


@pytest.mark.parametrize("name", ["rag", "monitoring"])
@pytest.mark.parametrize("question", ["", None, 123, "x" * 2001])
def test_invalid_input_is_rejected_before_backend(name, question):
    module = module_for(name)
    with patch.object(module, "get_agent") as factory:
        response = TestClient(module.app).post("/query", json={"question": question})
    assert response.status_code == 422
    factory.assert_not_called()


@pytest.mark.parametrize("name,failure,status", [
    ("rag", RuntimeError("private backend details"), 503),
    ("rag", TimeoutError("private backend details"), 503),
    ("rag", OperationalError("private backend details"), 503),
    ("rag", ConnectionError("private backend details"), 503),
    ("rag", AttributeError("private backend details"), 500),
    ("monitoring", MonitoringClientError("private backend details"), 503),
    ("monitoring", TimeoutError("private backend details"), 503),
    ("monitoring", ConnectionError("private backend details"), 503),
    ("monitoring", KeyError("private backend details"), 500),
])
def test_failures_are_safe_non_success_responses(name, failure, status, caplog):
    module = module_for(name)
    with patch.object(module, "get_agent", return_value=Mock(ask=Mock(side_effect=failure))):
        response = TestClient(module.app).post("/query", json={"question": "runbook alerts?"})
    assert response.status_code == status
    assert "private backend details" not in response.text + caplog.text


@pytest.mark.parametrize("name,reply", [
    ("rag", None),
    ("rag", SimpleNamespace(answer="broken")),
    ("rag", AgentResponse(answer="", sources=[])),
    ("rag", AgentResponse(answer="   ", sources=[])),
    ("rag", AgentResponse(answer="valid", sources=[object()])),
    ("rag", AgentResponse(answer="valid", retrieved_chunks=-1)),
    ("monitoring", None),
    ("monitoring", {"sources": []}),
    ("monitoring", {"answer": ""}),
    ("monitoring", {"answer": "   "}),
    ("monitoring", {"answer": "valid", "sources": [object()]}),
    ("monitoring", {"answer": "valid", "data": {"value": object()}}),
    ("monitoring", {"answer": "valid", "data": {"value": float("nan")}}),
])
def test_invalid_or_unserializable_agent_output_is_500(name, reply):
    module = module_for(name)
    with patch.object(module, "get_agent", return_value=Mock(ask=Mock(return_value=reply))):
        response = TestClient(module.app).post("/query", json={"question": "runbook alerts?"})
    assert response.status_code == 500
    assert "invalid response" in response.json()["detail"]


@pytest.mark.parametrize("name", ["rag", "monitoring"])
def test_real_query_handler_recovers_from_failure_over_kafka(name):
    module = module_for(name)
    broker = FakeBroker()
    bus = KafkaAgentBus(producer_factory=broker.producer, consumer_factory=broker.consumer)
    worker = AgentWorker(module.app, name, producer_factory=broker.producer, consumer_factory=broker.consumer)
    failure = RuntimeError("injected failure") if name == "rag" else MonitoringClientError("injected failure")
    agent = Mock(ask=Mock(side_effect=[failure, failure, valid_reply(name)]))
    try:
        with patch.object(module, "get_agent", return_value=agent):
            bus.start()
            worker.start()
            wait_until(lambda: broker.subscribers[request_topic(name)])
            query = AgentQuery(question="runbook alerts?", request_id="r")
            failed = asyncio.run(call_agent(name, query, bus=bus))
            assert failed.error.code == "unavailable" and agent.ask.call_count == 2
            recovered = asyncio.run(call_agent(name, query, bus=bus))
            assert recovered.status == "ok" and recovered.sources
            assert not bus._pending
    finally:
        bus.stop()
        worker.stop()


@pytest.mark.parametrize("failed_name", ["rag", "monitoring"])
def test_parallel_real_handlers_keep_healthy_agent_and_sources(failed_name):
    broker = FakeBroker()
    bus = KafkaAgentBus(producer_factory=broker.producer, consumer_factory=broker.consumer)
    workers = []
    rag_agent = Mock(ask=Mock(return_value=valid_reply("rag")))
    monitoring_agent = Mock(ask=Mock(return_value=valid_reply("monitoring")))
    failed = rag_agent if failed_name == "rag" else monitoring_agent
    failed.ask.return_value = None
    try:
        with patch.object(rag_main, "get_agent", return_value=rag_agent), patch.object(monitoring_main, "get_agent", return_value=monitoring_agent):
            bus.start()
            for name in ("rag", "monitoring"):
                worker = AgentWorker(module_for(name).app, name, producer_factory=broker.producer, consumer_factory=broker.consumer)
                workers.append(worker)
                worker.start()
                wait_until(lambda name=name: broker.subscribers[request_topic(name)])
            graph = build_orchestrator_graph(llm=FakeLLM('{"agents":["rag","monitoring"]}'), synth_llm=None, bus=bus)
            out = asyncio.run(graph.ainvoke({"question": "runbook alerts?", "request_id": "r", "results": []}))
            assert out["status"] == "partial"
            assert f"Unavailable: {failed_name} (agent_error)" in out["final_answer"]
            healthy_name = "monitoring" if failed_name == "rag" else "rag"
            source = "alertmanager:alerts" if healthy_name == "monitoring" else "runbook.md"
            assert out["sources"] == [source] and f"[{source}]" in out["final_answer"]
    finally:
        bus.stop()
        for worker in workers:
            worker.stop()
