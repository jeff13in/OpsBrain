"""Four real agent apps over the Kafka bus; all external backends controlled."""

import asyncio
from functools import lru_cache

import boto3
import httpx
import pytest
from monitoring import main as monitoring_main
from monitoring.agent import MonitoringAgent
from moto import mock_aws
from rag import main as rag_main
from rag.agent import RAGAgent

from agents.code import main as code_main
from agents.code.agent import CodeAgent, CodeClientError, CodeConfig
from agents.infra import main as infra_main
from agents.infra.agent import InfraAgent, InfraConfig
from orchestrator import main
from orchestrator.graph import build_orchestrator_graph
from orchestrator.memory import SessionMemory
from shared.agent_bus import REPLY_TOPIC, AgentWorker, KafkaAgentBus, request_topic
from shared.models import AskResponse, KafkaAgentReply, KafkaAgentRequest
from tests.test_agent_bus import FakeBroker, wait_until
from tests.test_week2_integration import RunbookRetriever

QUESTION = "Explain the runbook procedure for alerts, EC2 and commits"


@pytest.fixture
def four_agent_pipeline(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    broker = FakeBroker()
    bus = KafkaAgentBus(producer_factory=broker.producer, consumer_factory=broker.consumer)
    workers = []
    monitoring = MonitoringAgent()
    code = CodeAgent(CodeConfig(github_repo="fixture/app"))
    monkeypatch.setattr(monitoring, "_request_json", lambda *a, **k: [])
    monkeypatch.setattr(code, "_request_json", lambda *a, **k: [{
        "sha": "1234567890abcdef", "commit": {
            "message": "Fix alert handling", "author": {"name": "Fixture"}
        }, "html_url": "https://github.com/fixture/app/commit/1234567890abcdef"
    }])
    with mock_aws():
        boto3.client("ec2", region_name="us-east-1").run_instances(
            ImageId="ami-12345678", MinCount=1, MaxCount=1)
        agents = [
            ("rag", rag_main, RAGAgent(retriever=RunbookRetriever())),
            ("monitoring", monitoring_main, monitoring),
            ("infra", infra_main, InfraAgent(InfraConfig(aws_region="us-east-1"))),
            ("code", code_main, code),
        ]
        for _, module, agent in agents:
            monkeypatch.setattr(module, "get_agent", lambda agent=agent: agent)
        graph = build_orchestrator_graph(bus=bus)
        monkeypatch.setattr(main, "get_graph", lru_cache(maxsize=1)(lambda: graph))
        monkeypatch.setattr(main, "memory", SessionMemory())
        try:
            bus.start()
            for name, module, _ in agents:
                worker = AgentWorker(module.app, name, producer_factory=broker.producer,
                                     consumer_factory=broker.consumer)
                workers.append(worker)
                worker.start()
                wait_until(lambda name=name: broker.subscribers[request_topic(name)])
            wait_until(bus._ready.is_set)
            yield broker, bus, code
        finally:
            for worker in workers:
                worker.stop()
            bus.stop()


def ask_many(questions):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://orchestrator") as client:
            return await asyncio.gather(*[
                client.post("/ask", json={"question": question, "session_id": f"session-{i}"})
                for i, question in enumerate(questions)
            ])
    return asyncio.run(run())


def test_four_real_agents_succeed_over_serialized_kafka_pipeline(four_agent_pipeline):
    broker, bus, _ = four_agent_pipeline
    response = ask_many([QUESTION])[0]
    body = AskResponse.model_validate(response.json())
    assert response.status_code == 200 and body.status == "ok"
    assert body.routing.agents == ["rag", "monitoring", "infra", "code"]
    assert [r.agent for r in body.results] == body.routing.agents
    assert all(r.status == "ok" for r in body.results)
    assert body.sources == ["alerts.md", "alertmanager:alerts", "aws:ec2", "github:commits"]
    assert body.results[2].data["total"] == 1
    assert body.results[3].data["commits"][0]["message"] == "Fix alert handling"
    assert "[alerts.md]" in body.answer
    assert "Unavailable:" not in body.answer
    assert main.memory.history("session-0")[-1]["content"] == body.answer
    requests = [KafkaAgentRequest.model_validate(broker.sent_to(request_topic(name))[0])
                for name in body.routing.agents]
    replies = [KafkaAgentReply.model_validate(raw) for raw in broker.sent_to(REPLY_TOPIC)]
    assert {r.query.request_id for r in requests} == {body.request_id}
    assert {r.correlation_id for r in requests} == {r.correlation_id for r in replies}
    assert not bus._pending


def test_concurrent_four_agent_requests_do_not_cross_replies(four_agent_pipeline):
    broker, bus, _ = four_agent_pipeline
    questions = [f"{QUESTION}, request {i}" for i in range(4)]
    responses = ask_many(questions)
    bodies = [AskResponse.model_validate(r.json()) for r in responses]
    assert all(r.status_code == 200 for r in responses)
    assert [b.question for b in bodies] == questions
    assert all(b.status == "ok" and len(b.results) == 4 for b in bodies)
    assert len({b.request_id for b in bodies}) == 4
    for body in bodies:
        requests = [KafkaAgentRequest.model_validate(raw)
                    for name in body.routing.agents for raw in broker.sent_to(request_topic(name))
                    if raw["query"]["request_id"] == body.request_id]
        assert len(requests) == 4
        assert {r.query.question for r in requests} == {body.question}
    assert len(broker.sent_to(REPLY_TOPIC)) == 16
    assert not bus._pending


def test_code_outage_preserves_three_real_agent_answers(four_agent_pipeline, monkeypatch):
    broker, bus, code = four_agent_pipeline

    def unavailable(*args, **kwargs):
        raise CodeClientError("Controlled backend outage", status_code=503)

    monkeypatch.setattr(code, "_request_json", unavailable)
    response = ask_many([QUESTION])[0]
    body = AskResponse.model_validate(response.json())
    assert response.status_code == 200 and body.status == "partial"
    assert [r.status for r in body.results] == ["ok", "ok", "ok", "error"]
    assert body.results[-1].error.code == "unavailable"
    assert body.sources == ["alerts.md", "alertmanager:alerts", "aws:ec2"]
    assert "code (unavailable)" in body.answer
    assert len(broker.sent_to(request_topic("code"))) == 2
    assert not bus._pending
