"""Overload, runtime listener recovery and safe backend failure boundaries."""

import asyncio
import threading
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from agents.code import main as code_main
from agents.code.agent import CodeClientError
from agents.infra import main as infra_main
from agents.infra.agent import InfraAgent, InfraClientError, InfraConfig
from shared.agent_bus import REPLY_TOPIC, AgentWorker, KafkaAgentBus, request_topic
from shared.models import AgentQuery
from tests.test_agent_bus import FakeBroker, agent_app, wait_until
from tests.test_pipeline_resilience import envelope


def test_worker_overload_is_bounded_retryable_and_releases_capacity():
    worker = AgentWorker(agent_app(), "infra", max_concurrency=1, max_queue=1)
    worker._producer = Mock()
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def handle(raw):
        calls.append(raw["correlation_id"])
        entered.set()
        assert release.wait(2)

    try:
        with patch.object(worker, "handle", side_effect=handle):
            worker._submit(envelope(correlation_id="first"))
            assert entered.wait(1)
            worker._submit(envelope(correlation_id="queued"))
            worker._submit(envelope(correlation_id="overloaded"))
            worker._submit({"malformed": True})
            worker._submit(envelope(correlation_id="expired", deadline=1))
            worker._submit(envelope(correlation_id="wrong-agent", agent="code"))
            assert calls == ["first"]
            worker._producer.send.assert_called_once()
            topic, reply = worker._producer.send.call_args.args
            assert topic == REPLY_TOPIC
            assert reply.correlation_id == "overloaded" and reply.status_code == 503
            release.set()
            wait_until(lambda: len(calls) == 2)
            wait_until(lambda: worker._slots._value == 2)
            worker._submit(envelope(correlation_id="recovered"))
            wait_until(lambda: len(calls) == 3)
            assert calls == ["first", "queued", "recovered"]
    finally:
        release.set()
        worker.stop()


class FailedListener:
    def __init__(self):
        self.closed = False

    def listen(self, handler, stop=None, on_ready=None):
        if on_ready:
            on_ready()
        raise ConnectionError("private-upstream-error")

    def close(self):
        self.closed = True


@pytest.mark.parametrize("failed_side", ["worker", "bus"])
def test_listener_recovers_after_post_startup_failure(failed_side, caplog):
    broker = FakeBroker()
    failed = FailedListener()
    attempts = []

    def recovering_consumer(*args):
        attempts.append(args)
        return failed if len(attempts) == 1 else broker.consumer(*args)

    bus = KafkaAgentBus(producer_factory=broker.producer,
                        consumer_factory=recovering_consumer if failed_side == "bus" else broker.consumer)
    worker = AgentWorker(agent_app({"answer": "Recovered", "sources": ["fixture"]}), "infra",
                         producer_factory=broker.producer,
                         consumer_factory=recovering_consumer if failed_side == "worker" else broker.consumer)
    try:
        worker.start()
        bus.start()
        wait_until(lambda: len(attempts) >= 2 and failed.closed)
        wait_until(lambda: bus._ready.is_set() and broker.subscribers[request_topic("infra")])
        reply = asyncio.run(bus.request("infra", AgentQuery(question="pods?", request_id="after-recovery"), 2))
        assert reply.status_code == 200 and reply.body["answer"] == "Recovered"
        assert not bus._pending
        assert "private-upstream-error" not in caplog.text
    finally:
        worker.stop()
        bus.stop()


@pytest.mark.parametrize("module,error", [(infra_main, InfraClientError), (code_main, CodeClientError)])
@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_query_and_typed_endpoints_preserve_status_without_leaking_backend_text(module, error, status, caplog):
    agent = Mock()
    failure = error("https://user:secret-token@private.example/path?key=private-key", status_code=status)
    agent.ask.side_effect = failure
    agent.list_ec2_instances.side_effect = failure
    agent.list_commits.side_effect = failure
    typed_path = "/aws/instances" if module is infra_main else "/commits"
    with patch.object(module, "get_agent", return_value=agent):
        client = TestClient(module.app)
        for response in (client.post("/query", json={"question": "Check backend state"}), client.get(typed_path)):
            assert response.status_code == status
            assert "secret-token" not in response.text
            assert "private-key" not in response.text
            assert "private.example" not in response.text
            assert response.json()["detail"]
    assert "secret-token" not in caplog.text and "private-key" not in caplog.text


def test_partial_infra_health_does_not_expose_backend_errors_in_success_data():
    agent = InfraAgent(InfraConfig(aws_region="us-east-1"))
    failing = Mock(side_effect=InfraClientError("secret-token from upstream", status_code=500))
    checks = ["list_eks_clusters", "list_rds_instances", "list_nodes", "get_pod_health", "list_deployments"]
    with patch.multiple(agent, **dict.fromkeys(checks, failing), summarize_ec2=lambda: {"total": 1}), \
         patch.object(infra_main, "get_agent", return_value=agent):
        client = TestClient(infra_main.app)
        for response in (client.get("/health/summary"), client.post("/query", json={"question": "overall health"})):
            assert response.status_code == 200
            assert "secret-token" not in response.text
            assert "HTTP 500" in response.text
