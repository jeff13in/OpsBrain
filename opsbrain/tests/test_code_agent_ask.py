"""Code Agent ask(): every topic in the question is answered (OPU-101)."""

from __future__ import annotations

import pytest

from agents.code.agent import CodeAgent, CodeClientError, CodeConfig

COMMITS = {"repo": "o/r", "branch": None, "count": 1,
           "commits": [{"sha": "1234567890abcdef", "message": "Fix login"}]}
CI = {"repo": "o/r", "branch": None,
      "workflows": [{"workflow_name": "CI/CD", "branch": "main", "conclusion": "success", "status": "completed"}]}
PULLS = {"repo": "o/r", "state": "open", "count": 1,
         "pull_requests": [{"number": 4, "title": "Joint", "branch": "joint"}]}


@pytest.fixture
def agent(monkeypatch):
    agent = CodeAgent(CodeConfig(github_repo="o/r"))
    monkeypatch.setattr(agent, "list_commits", lambda: COMMITS)
    monkeypatch.setattr(agent, "summarize_ci", lambda: CI)
    monkeypatch.setattr(agent, "list_pull_requests", lambda state: {**PULLS, "pull_requests": [
        dict(pr) for pr in PULLS["pull_requests"]]})
    monkeypatch.setattr(agent, "get_pull_request_status", lambda number: {"overall": "success"})
    return agent


def test_commits_and_ci_are_both_answered(agent):
    result = agent.ask("What are the recent commits and did the latest CI/CD workflow runs pass?")

    assert result["sources"] == ["github:commits", "github:actions/runs"]
    assert "1234567 Fix login" in result["answer"]
    assert "CI/CD on main: success" in result["answer"]
    assert set(result["data"]) == {"commits", "ci"}


def test_open_pulls_include_check_status_when_asked(agent):
    result = agent.ask("Which pull requests are open and what is their check status?")

    assert result["sources"] == ["github:pulls"]
    assert result["answer"] == "1 open pull request(s) on o/r — #4 Joint (joint, CI success)."


def test_procedure_is_not_a_pull_request_and_single_topic_keeps_flat_data(agent):
    result = agent.ask("Explain the runbook procedure for alerts, EC2 and commits")

    assert result["sources"] == ["github:commits"]
    assert result["data"] == COMMITS


def test_partial_github_failure_is_reported_without_backend_detail(agent, monkeypatch):
    def fail():
        raise CodeClientError("token ghp_secret rejected", status_code=500)

    monkeypatch.setattr(agent, "summarize_ci", fail)
    result = agent.ask("Show recent commits and CI runs")

    assert result["sources"] == ["github:commits"]
    assert "Couldn't read ci from GitHub." in result["answer"]
    assert "ghp_secret" not in result["answer"]
