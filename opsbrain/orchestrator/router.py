"""Orchestrator router — routing contract (OPU-42).

Maps a question to the agents that should answer it. The contract:

  * route() always returns a RoutingDecision with at least one agent.
  * Agents appear in AGENT_REGISTRY order, so results/sources are stable.
  * Keyword matching is the deterministic baseline; the LLM classifier (OPU-43)
    must return the same RoutingDecision shape and fall back to this on failure.
  * Nothing matched → RAG, because runbooks are the broadest source.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from shared.models import AgentName, RoutingDecision


@dataclass(frozen=True)
class AgentSpec:
    url: str
    description: str          # shown to the LLM classifier in OPU-43
    keywords: tuple[str, ...]
    timeout_s: float = 30.0
    query_path: str = "/query"


# Service URLs default to the docker-compose / k8s service names and can be
# overridden per agent, e.g. RAG_AGENT_URL=http://localhost:8001.
AGENT_REGISTRY: dict[AgentName, AgentSpec] = {
    "rag": AgentSpec(
        url=os.getenv("RAG_AGENT_URL", "http://rag-agent:8001"),
        description="Runbooks and internal docs: how-to, troubleshooting steps, procedures.",
        keywords=("runbook", "how do i", "how to", "procedure", "docs", "documentation", "troubleshoot", "fix"),
        timeout_s=60.0,  # Gemini "thinking" model is the slowest agent
    ),
    "monitoring": AgentSpec(
        url=os.getenv("MONITORING_AGENT_URL", "http://monitoring-agent:8002"),
        description="Live metrics and alerts from Prometheus, Grafana, Alertmanager.",
        keywords=("alert", "metric", "prometheus", "grafana", "latency", "error rate", "firing", "dashboard"),
    ),
    "infra": AgentSpec(
        url=os.getenv("INFRA_AGENT_URL", "http://infra-agent:8003"),
        description="AWS (EC2, EKS, RDS) and Kubernetes state: pods, nodes, deployments, resource usage, Terraform.",
        keywords=("pod", "node", "kubernetes", "k8s", "eks", "ec2", "rds", "terraform", "cluster", "cpu", "memory", "aws"),
    ),
    "code": AgentSpec(
        url=os.getenv("CODE_AGENT_URL", "http://code-agent:8004"),
        description="GitHub: pull requests, commits, CI workflow runs, deployments.",
        keywords=("pr", "pull request", "commit", "ci", "pipeline", "workflow", "github", "build", "merge"),
    ),
}

DEFAULT_AGENT: AgentName = "rag"


def _matches(question: str, keyword: str) -> bool:
    return re.search(rf"\b{re.escape(keyword)}\b", question) is not None


def route(question: str) -> RoutingDecision:
    """Return the agents that should handle this question."""
    q = question.lower()
    matched: dict[AgentName, list[str]] = {}
    for name, spec in AGENT_REGISTRY.items():
        hits = [k for k in spec.keywords if _matches(q, k)]
        if hits:
            matched[name] = hits

    if not matched:
        return RoutingDecision(agents=[DEFAULT_AGENT], method="fallback", reason="No agent keywords matched; defaulting to runbooks.")

    reason = "; ".join(f"{name}: {', '.join(hits)}" for name, hits in matched.items())
    return RoutingDecision(agents=list(matched), method="keyword", reason=reason)
