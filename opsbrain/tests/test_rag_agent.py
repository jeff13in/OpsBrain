"""Unit tests for the RAG agent's retrieval and grounding behavior."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rag.agent import RAGAgent
from rag.retriever import RetrievedChunk


class FakeRetriever:
    config = SimpleNamespace(default_top_k=4)

    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks

    def retrieve(self, question: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        return self.chunks[:top_k]

    def build_context(self, chunks: list[RetrievedChunk]) -> str:
        return "\n".join(chunk.content for chunk in chunks)


class RAGAgentTests(unittest.TestCase):
    def test_returns_grounded_fallback_answer_for_retrieved_context(self) -> None:
        retriever = FakeRetriever(
            [
                RetrievedChunk(
                    id="1",
                    source="high-cpu.md",
                    content="Check CPU usage and scale the API deployment.",
                    score=0.9,
                )
            ]
        )
        agent = RAGAgent(retriever=retriever)

        with patch.dict("os.environ", {"LLM_API_KEY": ""}):
            response = agent.ask("How should I handle high CPU usage?")

        self.assertTrue(response.grounded)
        self.assertEqual(response.sources, ["high-cpu.md"])
        self.assertEqual(response.retrieved_chunks, 1)
        self.assertIn("[high-cpu.md]", response.answer)

    def test_reports_ungrounded_when_nothing_is_retrieved(self) -> None:
        agent = RAGAgent(retriever=FakeRetriever([]))

        with patch.dict("os.environ", {"LLM_API_KEY": ""}):
            response = agent.ask("How should I handle high CPU usage?")

        self.assertFalse(response.grounded)
        self.assertEqual(response.retrieved_chunks, 0)
        self.assertTrue(
            any("No relevant context" in error for error in response.validation_errors)
        )


if __name__ == "__main__":
    unittest.main()
