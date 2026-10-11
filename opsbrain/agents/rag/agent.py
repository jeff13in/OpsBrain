"""LangGraph-powered RAG agent for OpsBrain."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - handled with sequential fallback
    END = START = StateGraph = None

try:
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:  # pragma: no cover - handled with extractive fallback
    HumanMessage = SystemMessage = None

from rag.retriever import PgVectorRetriever, RetrievedChunk, RetrieverConfig
from shared.llm import ChatConfigurationError, get_chat_model

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the OpsBrain RAG agent for DevOps runbooks.
Answer the user using only the retrieved context.
If the context is not enough, say that clearly instead of guessing.
Keep the response concise and include source citations in square brackets like [runbook.md]."""

# Only bracketed content shaped like a filename (word chars/dashes/slashes ending in
# a dot-extension) counts as a claimed citation. Runbooks are full of shell syntax
# (e.g. `[ -z "$VAR" ]`) and markdown that also uses square brackets, so a bare
# `\[([^\]]+)\]` match would false-positive on those and discard good answers.
CITATION_PATTERN = re.compile(r"\[([\w.\-/]+\.[A-Za-z0-9]+)\]")


class AgentState(TypedDict, total=False):
    question: str
    top_k: int
    chunks: list[RetrievedChunk]
    context: str
    validation_errors: list[str]
    answer: str
    sources: list[str]


@dataclass(slots=True)
class AgentResponse:
    answer: str
    sources: list[str] = field(default_factory=list)
    grounded: bool = True
    validation_errors: list[str] = field(default_factory=list)
    retrieved_chunks: int = 0


class RAGAgent:
    """Retrieve relevant context, validate it, and synthesize an answer."""

    def __init__(
        self,
        retriever: PgVectorRetriever | None = None,
        *,
        llm: Any | None = None,
    ) -> None:
        self.retriever = retriever or PgVectorRetriever(RetrieverConfig())
        self._llm = llm
        self._graph = self._build_graph()

    def ask(self, question: str, *, top_k: int | None = None) -> AgentResponse:
        """Answer a question using retrieved pgvector context."""

        initial_state: AgentState = {
            "question": question.strip(),
            "top_k": top_k or self.retriever.config.default_top_k,
            "validation_errors": [],
        }
        if not initial_state["question"]:
            raise ValueError("Question cannot be empty.")

        if self._graph is not None:
            final_state = self._graph.invoke(initial_state)
        else:
            final_state = self._run_sequential(initial_state)

        answer = final_state.get("answer", "").strip()
        validation_errors = final_state.get("validation_errors", [])
        sources = final_state.get("sources", [])
        return AgentResponse(
            answer=answer,
            sources=sources,
            grounded=not validation_errors and bool(final_state.get("chunks")),
            validation_errors=validation_errors,
            retrieved_chunks=len(final_state.get("chunks", [])),
        )

    def _build_graph(self) -> Any | None:
        if StateGraph is None:
            return None

        graph = StateGraph(AgentState)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("validate_context", self._validate_context)
        graph.add_node("synthesize", self._synthesize)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "validate_context")
        graph.add_edge("validate_context", "synthesize")
        graph.add_edge("synthesize", END)
        return graph.compile()

    def _run_sequential(self, state: AgentState) -> AgentState:
        for step in (self._retrieve, self._validate_context, self._synthesize):
            state = step(state)
        return state

    def _retrieve(self, state: AgentState) -> AgentState:
        chunks = self.retriever.retrieve(
            state["question"],
            top_k=state.get("top_k"),
        )
        return {
            **state,
            "chunks": chunks,
            "context": self.retriever.build_context(chunks),
            "sources": [chunk.source for chunk in chunks],
        }

    def _validate_context(self, state: AgentState) -> AgentState:
        errors = list(state.get("validation_errors", []))
        chunks = state.get("chunks", [])
        if not chunks:
            errors.append("No relevant context was retrieved for the question.")
            return {**state, "validation_errors": errors}

        if not state.get("context", "").strip():
            errors.append("Retrieved context was empty after prompt preparation.")

        question_terms = {
            token
            for token in re.findall(r"[a-z0-9]{4,}", state["question"].lower())
        }
        context_terms = {
            token
            for chunk in chunks
            for token in re.findall(r"[a-z0-9]{4,}", chunk.content.lower())
        }
        overlap = question_terms & context_terms
        if question_terms and not overlap:
            errors.append(
                "Retrieved context has weak lexical overlap with the question."
            )
        return {**state, "validation_errors": errors}

    def _synthesize(self, state: AgentState) -> AgentState:
        chunks = state.get("chunks", [])
        errors = list(state.get("validation_errors", []))
        if not chunks:
            return {
                **state,
                "answer": (
                    "I couldn't find enough relevant runbook context to answer "
                    "that question confidently."
                ),
            }

        if self._llm_available():
            try:
                answer = self._generate_with_llm(state["question"], state["context"])
            except Exception as exc:  # noqa: BLE001 - preserve retrieved evidence on provider failure
                logger.warning("Chat answer generation failed; using retrieved snippets: %s", type(exc).__name__)
                answer = self._fallback_answer(state["question"], chunks, errors)
        else:
            answer = self._fallback_answer(state["question"], chunks, errors)

        answer = self._validate_answer(answer, chunks, errors)
        return {
            **state,
            "answer": answer,
            "validation_errors": errors,
            "sources": [chunk.source for chunk in chunks],
        }

    def _llm_available(self) -> bool:
        if self._llm is not None:
            return True
        try:
            self._llm = get_chat_model("answer")
        except ChatConfigurationError:
            return False
        return True

    def _generate_with_llm(self, question: str, context: str) -> str:
        llm = self._llm
        if llm is None:
            llm = get_chat_model("answer")
            self._llm = llm

        response = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Question:\n{question}\n\n"
                        f"Retrieved context:\n{context}"
                    )
                ),
            ]
        )
        content = getattr(response, "content", response)
        if isinstance(content, list):
            return " ".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content).strip()
        return str(content).strip()

    def _fallback_answer(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        validation_errors: list[str],
    ) -> str:
        if validation_errors:
            return (
                "I found partial context, but it may not be strong enough to fully "
                "answer the question. Review the sources below.\n\n"
                + self._render_source_snippets(chunks)
            )

        intro = f"Based on the retrieved runbooks, here's the best grounded answer to: {question}"
        return intro + "\n\n" + self._render_source_snippets(chunks)

    def _render_source_snippets(self, chunks: list[RetrievedChunk]) -> str:
        snippets: list[str] = []
        for chunk in chunks[:3]:
            preview = chunk.content.strip().replace("\n", " ")
            if len(preview) > 280:
                preview = preview[:277].rstrip() + "..."
            snippets.append(f"[{chunk.source}] {preview}")
        return "\n".join(snippets)

    def _validate_answer(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
        validation_errors: list[str],
    ) -> str:
        cleaned = answer.strip()
        if not cleaned:
            validation_errors.append("The generated answer was empty.")
            cleaned = self._fallback_answer("", chunks, validation_errors)

        allowed_sources = {chunk.source for chunk in chunks}
        citations = CITATION_PATTERN.findall(cleaned)
        invalid_citations = [citation for citation in citations if citation not in allowed_sources]
        if invalid_citations:
            # Replace unsupported model citations with extractive, retrieved text.
            cleaned = self._fallback_answer("", chunks, validation_errors)
            citations = CITATION_PATTERN.findall(cleaned)

        if allowed_sources and not citations:
            cleaned = cleaned.rstrip() + "\n\nSources: " + ", ".join(f"[{source}]" for source in sorted(allowed_sources))
        return cleaned
