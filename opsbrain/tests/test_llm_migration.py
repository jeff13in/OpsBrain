"""OPU-80: deterministic factory, provider error, citation and pipeline checks."""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from langchain_openai import ChatOpenAI
from rag.agent import RAGAgent
from rag.retriever import RetrievedChunk, RetrieverConfig

from orchestrator import llm as llm_ops
from orchestrator import main
from orchestrator.graph import build_orchestrator_graph
from shared.llm import DEFAULT_MODELS, ChatConfigurationError, get_chat_model
from shared.models import AgentError, AgentResult
from tests.test_orchestrator_graph import FakeLLM, agent_transport, ok, run
from tests.test_rag_agent import FakeRetriever


@pytest.mark.parametrize("role", ["router", "answer", "synth"])
def test_factory_role_settings(role):
    with patch.dict("os.environ", {"LLM_API_KEY": "unit-test-key", "LLM_BASE_URL": "https://provider.example/v1", f"LLM_MODEL_{role.upper()}": f"custom-{role}"}, clear=True):
        with patch("shared.llm.ChatOpenAI") as constructor:
            get_chat_model(role)
    kwargs = constructor.call_args.kwargs
    assert kwargs["model"] == f"custom-{role}"
    assert kwargs["base_url"] == "https://provider.example/v1"
    assert kwargs["api_key"] == "unit-test-key"
    assert kwargs["max_retries"] == 0
    assert kwargs["use_responses_api"] is False
    assert kwargs["timeout"] == {"router": 10, "answer": 45, "synth": 20}[role]


@pytest.mark.parametrize("role", ["router", "answer", "synth"])
def test_factory_defaults_and_ollama(role):
    with patch.dict("os.environ", {"LLM_API_KEY": "unit-test-key"}, clear=True):
        assert get_chat_model(role).model_name == DEFAULT_MODELS[role]
    with patch.dict("os.environ", {"LLM_API_KEY": "ollama", "LLM_BASE_URL": "http://localhost:11434/v1", f"LLM_MODEL_{role.upper()}": "local-model"}, clear=True):
        model = get_chat_model(role)
    assert model.model_name == "local-model"
    assert model.openai_api_base == "http://localhost:11434/v1"


@pytest.mark.parametrize("role,settings,message", [
    ("invalid", {}, "role"),
    ("router", {}, "LLM_API_KEY"),
    ("answer", {"LLM_API_KEY": "..."}, "LLM_API_KEY"),
    ("synth", {"LLM_API_KEY": "test", "LLM_MODEL_SYNTH": ""}, "LLM_MODEL_SYNTH"),
    ("router", {"LLM_API_KEY": "test", "LLM_BASE_URL": ""}, "LLM_BASE_URL"),
    ("router", {"LLM_API_KEY": "test", "LLM_BASE_URL": "https://user:secret@example.com/v1"}, "LLM_BASE_URL"),
])
def test_invalid_configuration_has_clear_secret_free_errors(role, settings, message):
    with patch.dict("os.environ", settings, clear=True):
        with pytest.raises(ChatConfigurationError, match=message) as error:
            get_chat_model(role)
    assert "secret@" not in str(error.value)


def test_startup_resolves_independent_roles():
    main.get_graph.cache_clear()
    router_model, synth_model = Mock(), Mock()
    with patch("orchestrator.main.get_llm", side_effect=[router_model, synth_model]) as factory:
        with patch("orchestrator.main.build_orchestrator_graph") as build:
            main.get_graph()
    assert [call.args for call in factory.call_args_list] == [("router",), ("synth",)]
    build.assert_called_once_with(llm=router_model, synth_llm=synth_model)
    main.get_graph.cache_clear()


@pytest.mark.parametrize("reply", [
    '{"agents":"infra"}', '{"agents":["slack","infra"]}',
    '{"agents":[]}', '{"agents":["infra"],"standalone_question":42}',
    '{"agents":["infra"],"standalone_question":" "}',
])
def test_invalid_router_schema_uses_keyword_fallback(reply):
    out = run(build_orchestrator_graph(llm=FakeLLM(reply), transport=agent_transport({"infra": ok("pods ready", [])})), "Check Kubernetes pods")
    assert out["routing"].method == "keyword"
    assert out["routing"].agents == ["infra"]


def sdk_model(role, handler):
    """Use the actual LangChain/OpenAI client against a fake HTTP provider."""
    transport = httpx.MockTransport(handler)
    original = ChatOpenAI
    with patch.dict("os.environ", {"LLM_API_KEY": "test", "LLM_BASE_URL": "https://provider.example/v1"}, clear=True):
        with patch("shared.llm.ChatOpenAI", side_effect=lambda **kwargs: original(
            **kwargs, http_client=httpx.Client(transport=transport),
            http_async_client=httpx.AsyncClient(transport=transport),
        )):
            return get_chat_model(role)


def test_real_sdk_429_router_no_retry_under_one_second():
    calls = []

    def rate_limited(request):
        calls.append(json.loads(request.content))
        return httpx.Response(429, headers={"retry-after": "60"}, json={"error": {"message": "quota", "type": "rate_limit_error"}})

    model = sdk_model("router", rate_limited)
    started = time.monotonic()
    out = run(build_orchestrator_graph(llm=model, transport=agent_transport({"infra": ok("pods ready", [])})), "Check Kubernetes pods")
    assert time.monotonic() - started < 1
    assert len(calls) == 1
    assert calls[0]["model"] == "openai/gpt-oss-20b"
    assert out["routing"].method == "keyword"
    assert out["final_answer"] == "pods ready"


def test_actual_chat_completion_json_is_schema_valid():
    reply = json.dumps({"agents": ["code", "infra", "infra"], "standalone_question": "Check PR and pods", "reason": "deploy"})

    def response(request):
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0, "model": "test", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": reply}}]})

    result = asyncio.run(llm_ops.classify(sdk_model("router", response), "Check PR and pods", []))
    assert result[0].agents == ["infra", "code"]
    assert result[0].method == "llm"
    assert result[1] == "Check PR and pods"


class SlowModel:
    def __init__(self):
        self.cancelled = False

    async def ainvoke(self, messages):
        try:
            await asyncio.sleep(30)
        finally:
            self.cancelled = True


def test_router_deadline_cancels_call_and_routes_by_keyword():
    model = SlowModel()
    with patch.object(llm_ops, "ROUTING_TIMEOUT_SECONDS", 0.01):
        out = run(build_orchestrator_graph(llm=model, transport=agent_transport({"infra": ok("A", [])})), "Check Kubernetes pods")
    assert model.cancelled
    assert out["routing"].method == "keyword"
    assert llm_ops.ROUTING_TIMEOUT_SECONDS == 10


RESULTS = [
    AgentResult(agent="rag", status="ok", answer="Scale API [runbook-high-cpu.md]", sources=["runbook-high-cpu.md"]),
    AgentResult(agent="infra", status="ok", answer="2 pods", sources=["kubernetes:pods"]),
    AgentResult(agent="code", status="error", error=AgentError(code="unavailable", message="offline", retryable=True)),
]


def test_synthesis_keeps_citations_and_unavailable_agents():
    model = FakeLLM("", "Scale API [runbook-high-cpu.md]; there are 2 pods.")
    answer = asyncio.run(llm_ops.synthesise(model, "CPU?", RESULTS))
    assert "[runbook-high-cpu.md]" in answer
    assert "[kubernetes:pods]" in answer
    assert "Unavailable: code (unavailable)" in answer
    assert "[code] UNAVAILABLE (unavailable)" in model.prompts[0]


@pytest.mark.parametrize("failure", ["429", "timeout", "error", "empty"])
def test_synthesis_failure_keeps_all_available_answers(failure):
    calls = []

    def rate_limited(request):
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": "60"}, json={"error": {"message": "quota"}})

    model = sdk_model("synth", rate_limited) if failure == "429" else SlowModel()
    if failure == "empty":
        model = FakeLLM("", "")
    elif failure == "error":
        model = Mock(ainvoke=Mock(side_effect=RuntimeError("provider error")))
    router = FakeLLM('{"agents":["rag","infra","code"]}')
    graph = build_orchestrator_graph(llm=router, synth_llm=model, transport=agent_transport({"rag": ok(RESULTS[0].answer, RESULTS[0].sources), "infra": ok("2 pods", ["kubernetes:pods"]), "code": 500}))
    with patch.object(llm_ops, "SYNTHESIS_TIMEOUT_SECONDS", 0.01 if failure == "timeout" else 20):
        out = run(graph, "CPU and pods?")
    assert "[rag] Scale API [runbook-high-cpu.md]" in out["final_answer"]
    assert "[infra] 2 pods" in out["final_answer"]
    assert "Unavailable: code (agent_error)" in out["final_answer"]
    assert out["status"] == "partial"
    assert out["sources"] == ["runbook-high-cpu.md", "kubernetes:pods"]
    if failure == "429":
        assert len(calls) == 1
    if failure == "timeout":
        assert model.cancelled
    assert llm_ops.SYNTHESIS_TIMEOUT_SECONDS == 20


@pytest.mark.parametrize("question,source,content", [
    ("What should I do when CPU usage is high?", "runbook-high-cpu.md", "Check CPU usage and scale the API deployment."),
    ("How do I handle exhausted database connections?", "runbook-db-connections.md", "Check database connections and reduce connection pool size."),
])
def test_rag_answer_factory_citations_grounding_and_evidence(question, source, content):
    chunks = [RetrievedChunk(id="1", source=source, content=content, score=0.9)]
    model = Mock(invoke=Mock(return_value=SimpleNamespace(content=f"Follow the runbook [{source}]")))
    with patch("rag.agent.get_chat_model", return_value=model) as factory:
        answer = RAGAgent(retriever=FakeRetriever(chunks)).ask(question)
    factory.assert_called_once_with("answer")
    assert f"[{source}]" in answer.answer
    assert answer.grounded and answer.validation_errors == []
    assert answer.sources == [source] and answer.retrieved_chunks == 1
    assert content in model.invoke.call_args.args[0][1].content


@pytest.mark.parametrize("generated", ["Check CPU", "Check CPU [made-up.md]", ""])
def test_rag_citation_validation_survives_missing_or_invalid_citations(generated):
    model = Mock(invoke=Mock(return_value=SimpleNamespace(content=generated)))
    chunks = [RetrievedChunk(id="1", source="runbook-high-cpu.md", content="Check CPU usage", score=0.9)]
    answer = RAGAgent(retriever=FakeRetriever(chunks), llm=model).ask("Check CPU usage")
    assert "[runbook-high-cpu.md]" in answer.answer
    assert "made-up.md" not in answer.answer
    assert answer.grounded == bool(generated)


def test_rag_provider_failure_uses_grounded_snippets():
    model = Mock(invoke=Mock(side_effect=httpx.ReadTimeout("slow")))
    chunks = [RetrievedChunk(id="1", source="runbook-high-cpu.md", content="Check CPU usage", score=0.9)]
    answer = RAGAgent(retriever=FakeRetriever(chunks), llm=model).ask("Check CPU usage")
    assert answer.grounded
    assert "[runbook-high-cpu.md]" in answer.answer


def test_embedding_configuration_is_unchanged():
    with patch.dict("os.environ", {}, clear=True):
        assert RetrieverConfig().embedding_model == "models/gemini-embedding-001"


def test_rag_actual_sdk_429_has_no_retry_and_retains_evidence():
    calls = []

    def rate_limited(request):
        calls.append(json.loads(request.content))
        return httpx.Response(429, headers={"retry-after": "60"}, json={"error": {"message": "quota"}})

    chunks = [RetrievedChunk(id="1", source="runbook-high-cpu.md", content="Check CPU usage", score=0.9)]
    answer = RAGAgent(retriever=FakeRetriever(chunks), llm=sdk_model("answer", rate_limited)).ask("Check CPU usage")
    assert len(calls) == 1 and calls[0]["model"] == "openai/gpt-oss-120b"
    assert answer.grounded and "[runbook-high-cpu.md]" in answer.answer


def test_all_four_agents_fan_out_concurrently_with_independent_synthesis():
    active, peak = 0, 0

    async def handler(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return httpx.Response(200, json=ok("Available evidence", ["runbook-high-cpu.md"]))

    router = FakeLLM('{"agents":["rag","monitoring","infra","code"]}')
    synth = FakeLLM("", "Combined findings [runbook-high-cpu.md]")
    out = run(build_orchestrator_graph(llm=router, synth_llm=synth, transport=httpx.MockTransport(handler)), "Investigate high CPU across all systems")
    assert peak == 4
    assert out["status"] == "ok" and len(out["results"]) == 4
    assert out["final_answer"] == "Combined findings [runbook-high-cpu.md]"
    assert len(router.prompts) == len(synth.prompts) == 1
