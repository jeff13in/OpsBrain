"""Record live Groq routing, RAG API, synthesis and async HTTP pipeline checks.

Run from opsbrain: python -m scripts.validate_chat
Requires explicitly configured LLM_API_KEY, running APIs and their backend
credentials. Does not ingest documents or execute operational write endpoints.
The reconstructed question set is not an original OPU-51 execution record.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from orchestrator import llm as llm_ops
from orchestrator.graph import build_orchestrator_graph
from shared.llm import DEFAULT_BASE_URL, DEFAULT_MODELS, get_chat_model
from shared.models import AgentError, AgentResult, AskResponse


async def validate(args):
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "live-provider-and-live-HTTP-services",
        "models": {role: os.getenv(f"LLM_MODEL_{role.upper()}", default) for role, default in DEFAULT_MODELS.items()},
        "transport": "Direct graph uses HTTP; deployed /ask uses its configured transport",
        "question_set": args.questions,
        "question_set_origin": "Reconstructed from repository runbooks and Linear OPU-51 scope; no original question set exists here",
        "checks": [],
    }
    checks = report["checks"]
    # Never serialize env vars, key values, URLs with credentials, or exceptions.
    if not os.getenv("LLM_API_KEY", "").strip() or os.getenv("LLM_API_KEY") == "...":
        checks.append({"name": "live-validation", "status": "not-executed", "reason": "LLM_API_KEY is not configured"})
        return report, 2

    router, synth = get_chat_model("router"), get_chat_model("synth")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/") + "/models",
                headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"]},
            )
            response.raise_for_status()
            available = {item["id"] for item in response.json()["data"]}
            missing = [model for model in report["models"].values() if model not in available]
            checks.append({"name": "provider-model-discovery", "status": "failed" if missing else "passed", "missing_models": missing})
    except Exception as exc:  # noqa: BLE001 - diagnostics must not expose tokens/provider errors
        checks.append({"name": "provider-model-discovery", "status": "failed", "error_type": type(exc).__name__})

    for case in questions:
        started = asyncio.get_running_loop().time()
        result = await llm_ops.classify(router, case["question"], [])
        matches = result is not None and set(result[0].agents) == set(case["agents"])
        checks.append({"name": "routing", "case": case["id"], "status": "passed" if matches else "failed", "expected_agents": case["agents"], "routing": result[0].model_dump() if result else None, "seconds": round(asyncio.get_running_loop().time() - started, 3)})

    async with httpx.AsyncClient(timeout=90) as client:
        for case in (case for case in questions if "expected_source" in case):
            try:
                response = await client.post(args.rag_url.rstrip("/") + "/query", json={"question": case["question"], "top_k": 4})
                response.raise_for_status()
                body = response.json()
                citation = f"[{case['expected_source']}]"
                answer = body.get("answer", "")
                extractive = answer.startswith(("Based on the retrieved runbooks", "I found partial context"))
                valid = body.get("grounded") is True and body.get("validation_errors") == [] and citation in answer
                checks.append({"name": "rag-api", "case": case["id"], "status": "passed" if valid and not extractive else "failed", "grounded": body.get("grounded"), "citation_present": citation in answer, "extractive_fallback_detected": extractive, "sources": body.get("sources"), "answer": answer})
            except Exception as exc:  # noqa: BLE001
                checks.append({"name": "rag-api", "case": case["id"], "status": "failed", "error_type": type(exc).__name__})

    # Real provider call over explicitly synthetic agent summaries; independent
    # of backend access and clearly distinct from the full pipeline check.
    summaries = [
        AgentResult(agent="rag", status="ok", answer="Scale API [runbook-high-cpu.md]", sources=["runbook-high-cpu.md"]),
        AgentResult(agent="infra", status="ok", answer="Two pods are ready.", sources=["kubernetes:pods"]),
        AgentResult(agent="code", status="error", error=AgentError(code="unavailable", message="controlled fixture", retryable=True)),
    ]
    answer = await llm_ops.synthesise(synth, "Summarize high CPU findings", summaries)
    valid = bool(answer) and all(token in answer for token in ("[runbook-high-cpu.md]", "[kubernetes:pods]", "code (unavailable)"))
    checks.append({"name": "live-synthesis-with-fixture-summaries", "status": "passed" if valid else "failed", "answer": answer})

    graph = build_orchestrator_graph(llm=router, synth_llm=synth)
    for case in questions:
        try:
            state = await graph.ainvoke({"request_id": "opu80-validation", "question": case["question"], "history": [], "results": []})
            results = state["results"]
            valid = state["status"] == "ok" and set(state["routing"].agents) == set(case["agents"])
            checks.append({"name": "async-HTTP-pipeline", "case": case["id"], "status": "passed" if valid else "failed", "pipeline_status": state["status"], "routing": state["routing"].model_dump(), "agent_results": [{"agent": r.agent, "status": r.status, "error_code": r.error.code if r.error else None, "sources": r.sources} for r in results], "answer": state["final_answer"]})
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "async-HTTP-pipeline", "case": case["id"], "status": "failed", "error_type": type(exc).__name__})

    # Exercise the deployed /ask contract in addition to the direct graph.
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(args.orchestrator_url.rstrip("/") + "/ask", json={"question": questions[0]["question"]})
            response.raise_for_status()
            body = AskResponse.model_validate(response.json())
            checks.append({"name": "deployed-ask-contract", "status": "passed" if body.status == "ok" else "failed", "pipeline_status": body.status})
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "deployed-ask-contract", "status": "failed", "error_type": type(exc).__name__})
    return report, int(any(check["status"] != "passed" for check in checks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default="validation/opu51-questions.json")
    parser.add_argument("--output", default="validation/opu80-live-results.json")
    parser.add_argument("--rag-url", default="http://localhost:8001")
    parser.add_argument("--orchestrator-url", default="http://localhost:8000")
    args = parser.parse_args()
    report, code = asyncio.run(validate(args))
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Validation evidence: {args.output}; exit code {code} (2 means not executed)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
