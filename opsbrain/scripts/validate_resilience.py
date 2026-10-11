"""OPU-60 live Kafka transport checks using isolated, explicitly synthetic agents.

No model, GitHub, AWS or Kubernetes calls. Requires KAFKA_BOOTSTRAP_SERVERS.
Unique topic/group prefixes prevent consuming operational agent messages.
"""

import argparse
import asyncio
import dataclasses
import json
import os
import threading
import time
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
from kafka import KafkaProducer as RawProducer

from orchestrator.graph import build_orchestrator_graph
from orchestrator.router import AGENT_REGISTRY
from shared.agent_bus import (
    REPLY_TOPIC,
    AgentBusUnavailable,
    AgentWorker,
    KafkaAgentBus,
    request_topic,
)
from shared.kafka_client import KafkaConsumer, KafkaProducer
from shared.models import AgentQuery


async def run_checks(bootstrap, real_rag_monitoring=False):
    prefix = f"opsbrain.validation.{uuid.uuid4().hex[:12]}."
    checks = []
    workers = []
    readiness = []
    state = {"code_failed": True}
    patches = ExitStack()

    class Producer:
        def __init__(self):
            self.inner = KafkaProducer(bootstrap)

        def send(self, topic, message):
            self.inner.send(prefix + topic, message)

        def close(self):
            self.inner.close()

    class Consumer:
        def __init__(self, topic, group, offset, ready=None):
            self.inner = KafkaConsumer(prefix + topic, bootstrap, prefix + group, offset)
            self.ready = ready

        def listen(self, handler, stop=None, on_ready=None):
            self.inner.listen(handler, stop, on_ready or (self.ready.set if self.ready else None))

        def close(self):
            self.inner.close()

    def app_for(name):
        if real_rag_monitoring and name in ("rag", "monitoring"):
            from monitoring import main as monitoring_main
            from monitoring.agent import MonitoringClientError
            from rag import main as rag_main
            from rag.agent import AgentResponse

            def ask(question, **kwargs):
                if state.get(f"{name}_outage"):
                    if name == "rag":
                        raise RuntimeError("Injected RAG dependency outage")
                    raise MonitoringClientError("Injected monitoring dependency outage")
                if name == "monitoring" and not state.get("monitoring_valid"):
                    return None  # invalid backend output, contained by the real endpoint
                if name == "rag":
                    return AgentResponse(answer=f"Fixture {question} [runbook.md]", sources=["runbook.md"],
                                         grounded=True, retrieved_chunks=1)
                return {"answer": "No alerts [alertmanager:alerts]", "sources": ["alertmanager:alerts"],
                        "data": {"alerts": {"total": 0}}}

            module = rag_main if name == "rag" else monitoring_main
            patches.enter_context(patch.object(module, "get_agent", return_value=Mock(ask=ask)))
            return module.app
        app = FastAPI()

        @app.post("/query")
        def query(body: dict):
            if name == "monitoring":
                return {"sources": []}  # intentionally incomplete successful response
            if name == "code" and state["code_failed"]:
                raise HTTPException(500, "Injected test failure")
            return {"answer": f"Fixture {body['request_id']} [runbook.md]", "sources": ["runbook.md"]}

        return app

    def record(name, passed):
        checks.append({"name": name, "status": "passed" if passed else "failed"})

    bus = KafkaAgentBus(producer_factory=Producer, consumer_factory=Consumer, ready_timeout_s=30)
    raw = None
    try:
        bus.start()
        for name in ("rag", "monitoring", "code"):
            ready = threading.Event()
            readiness.append(ready)
            worker = AgentWorker(app_for(name), name, producer_factory=Producer,
                                 consumer_factory=lambda topic, group, offset, ready=ready: Consumer(topic, group, offset, ready))
            workers.append(worker)
            worker.start()
        if not await asyncio.to_thread(bus._ready.wait, 45):
            raise RuntimeError("Kafka reply consumer not ready")
        for ready in readiness:
            if not await asyncio.to_thread(ready.wait, 45):
                raise RuntimeError("Kafka fixture worker not ready")
        raw = RawProducer(bootstrap_servers=bootstrap)
        # Send invalid UTF-8/JSON and invalid schema before a healthy request.
        for wire in (b"\xff", b"null", b"[]", b'{"deadline":NaN}', b'{"query":"invalid"}'):
            await asyncio.to_thread(lambda wire=wire: raw.send(prefix + request_topic("rag"), value=wire).get(timeout=10))
        healthy = await bus.request("rag", AgentQuery(question="runbook poison-recovery?", request_id="poison-recovery"), 10)
        record("poison-messages-do-not-stop-worker", "poison-recovery" in healthy.body["answer"])

        class Router:
            async def ainvoke(self, messages):
                return SimpleNamespace(content=json.dumps({"agents": ["rag", "monitoring", "infra", "code"]}))

        original = AGENT_REGISTRY["infra"]
        AGENT_REGISTRY["infra"] = dataclasses.replace(original, timeout_s=0.5)
        try:
            graph = build_orchestrator_graph(llm=Router(), synth_llm=None, bus=bus)
            out = await graph.ainvoke({"question": "Synthetic four-agent failure check", "request_id": "partial", "results": []})
        finally:
            AGENT_REGISTRY["infra"] = original
        outcomes = {r.agent: r for r in out["results"]}
        record("mixed-parallel-failures-retain-success", out["status"] == "partial" and out["sources"] == ["runbook.md"]
               and outcomes["monitoring"].error.code == ("agent_error" if real_rag_monitoring else "invalid_response")
               and outcomes["infra"].error.code == "timeout"
               and outcomes["code"].error.code == "agent_error" and "Unavailable:" in out["final_answer"])
        state["code_failed"] = False
        recovered = await bus.request("code", AgentQuery(question="commits?", request_id="recovered"), 10)
        record("agent-recovers-after-failed-response", recovered.status_code == 200)
        replies = await asyncio.gather(*(bus.request("rag", AgentQuery(question=f"runbook parallel-{i}?", request_id=f"parallel-{i}"), 15)
                                         for i in range(8)))
        record("eight-concurrent-replies-stay-correlated", all(f"parallel-{i}" in reply.body["answer"] for i, reply in enumerate(replies)))

        if real_rag_monitoring:
            state["monitoring_valid"] = True
            for name in ("rag", "monitoring"):
                state[f"{name}_outage"] = True
                failed = await bus.request(name, AgentQuery(question="runbook alerts?", request_id="outage"), 10)
                state[f"{name}_outage"] = False
                recovered = await bus.request(name, AgentQuery(question="runbook alerts?", request_id="recovered"), 10)
                record(f"real-{name}-dependency-failure-and-recovery", failed.status_code == 503
                       and recovered.status_code == 200 and bool(recovered.body["sources"]))

        missing = asyncio.create_task(bus.request("infra", AgentQuery(question="pods?", request_id="wrong-agent"), 1))
        async with asyncio.timeout(2):
            while not bus._pending:
                await asyncio.sleep(0.001)
        correlation = next(iter(bus._pending))
        wrong = json.dumps({"correlation_id": correlation, "agent": "code", "status_code": 200, "body": {"answer": "wrong"}}).encode()
        await asyncio.to_thread(lambda: raw.send(prefix + REPLY_TOPIC, value=wrong).get(timeout=10))
        try:
            await missing
            record("wrong-agent-reply-rejected", False)
        except TimeoutError:
            record("wrong-agent-reply-rejected", not bus._pending)
        pending = asyncio.create_task(bus.request("infra", AgentQuery(question="pods?", request_id="shutdown"), 60))
        async with asyncio.timeout(2):
            while not bus._pending:
                await asyncio.sleep(0.001)
        bus.stop()
        try:
            await asyncio.wait_for(pending, 1)
            record("shutdown-fails-pending-request", False)
        except AgentBusUnavailable:
            record("shutdown-fails-pending-request", not bus._pending)
    finally:
        bus.stop()
        for worker in workers:
            worker.stop()
        patches.close()
        if raw:
            raw.close(timeout=5)
    mode = "real-kafka-real-rag-monitoring-handlers-injected-backends-no-model-calls" if real_rag_monitoring else "real-kafka-synthetic-agents-no-model-calls"
    return {"timestamp": datetime.now(UTC).isoformat(), "mode": mode,
            "topic_prefix": prefix, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--real-rag-monitoring", action="store_true", help="Use real RAG/Monitoring query handlers with injected backends.")
    args = parser.parse_args()
    started = time.monotonic()
    try:
        report = asyncio.run(run_checks(os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"), args.real_rag_monitoring))
    except Exception as exc:  # noqa: BLE001 - do not emit broker credentials or payloads
        report = {"mode": "real-kafka-synthetic-agents-no-model-calls", "checks": [
            {"name": "live-check-execution", "status": "failed", "error_type": type(exc).__name__}]}
    report["seconds"] = round(time.monotonic() - started, 3)
    output = json.dumps(report, indent=2) + "\n"
    Path(args.output).write_text(output, encoding="utf-8")
    print(output)
    return int(any(check["status"] != "passed" for check in report["checks"]))


if __name__ == "__main__":
    raise SystemExit(main())
