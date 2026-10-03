"""Code agent utilities for GitHub pull requests and Actions CI status."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(slots=True)
class CodeConfig:
    github_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GITHUB_API_BASE_URL", "https://api.github.com"
        ).rstrip("/")
    )
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_repo: str = field(default_factory=lambda: os.getenv("GITHUB_REPO", ""))
    timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("CODE_TIMEOUT_SECONDS", "10"))
    )


class CodeClientError(RuntimeError):
    """Raised when GitHub cannot be queried successfully.

    `status_code` is what the HTTP layer returns (see orchestrator/CONTRACT.md):
    503 (default) when GitHub is unreachable, slow, erroring, or rate-limiting us;
    404/400 when the request names something that doesn't exist or is invalid;
    500 when the token/repo config is missing or lacks permission.
    """

    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class CodeAgent:
    """Answer questions about pull requests and CI/CD pipeline status via the GitHub API."""

    def __init__(self, config: CodeConfig | None = None) -> None:
        self.config = config or CodeConfig()

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "repo": self.config.github_repo or None,
            "github_token_configured": bool(self.config.github_token),
        }

    # ── Pull requests ────────────────────────────────────────────────────

    def list_pull_requests(
        self, *, state: str = "open", limit: int = 10
    ) -> dict[str, Any]:
        self._require_repo()
        payload = self._request_json(
            "GET",
            f"/repos/{self.config.github_repo}/pulls",
            params={"state": state, "per_page": min(limit, 100)},
        )
        pulls = [self._normalize_pr(pr) for pr in payload]
        return {"repo": self.config.github_repo, "state": state, "count": len(pulls), "pull_requests": pulls}

    def get_pull_request(self, number: int) -> dict[str, Any]:
        self._require_repo()
        payload = self._request_json(
            "GET", f"/repos/{self.config.github_repo}/pulls/{number}"
        )
        return self._normalize_pr(payload, detailed=True)

    def get_pull_request_status(self, number: int) -> dict[str, Any]:
        """Combined check-run + status summary for a PR's head commit."""
        pr = self.get_pull_request(number)
        sha = pr["head_sha"]
        checks_payload = self._request_json(
            "GET", f"/repos/{self.config.github_repo}/commits/{sha}/check-runs"
        )
        check_runs = [
            {
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
            }
            for run in checks_payload.get("check_runs", [])
        ]
        conclusions = Counter(run["conclusion"] or run["status"] for run in check_runs)
        overall = "success"
        if any(run["conclusion"] == "failure" for run in check_runs):
            overall = "failure"
        elif any(run["status"] != "completed" for run in check_runs):
            overall = "pending"
        elif not check_runs:
            overall = "unknown"
        return {
            "number": number,
            "head_sha": sha,
            "overall": overall,
            "breakdown": dict(conclusions),
            "check_runs": check_runs,
        }

    # ── Commits ──────────────────────────────────────────────────────────

    def list_commits(self, *, branch: str | None = None, limit: int = 10) -> dict[str, Any]:
        self._require_repo()
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if branch:
            params["sha"] = branch
        payload = self._request_json(
            "GET", f"/repos/{self.config.github_repo}/commits", params=params
        )
        commits = [self._normalize_commit(commit) for commit in payload]
        return {
            "repo": self.config.github_repo,
            "branch": branch,
            "count": len(commits),
            "commits": commits,
        }

    def get_commit(self, sha: str) -> dict[str, Any]:
        self._require_repo()
        payload = self._request_json(
            "GET", f"/repos/{self.config.github_repo}/commits/{sha}"
        )
        return self._normalize_commit(payload, detailed=True)

    # ── Deployments ──────────────────────────────────────────────────────

    def list_deployments(
        self, *, environment: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        self._require_repo()
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if environment:
            params["environment"] = environment
        payload = self._request_json(
            "GET", f"/repos/{self.config.github_repo}/deployments", params=params
        )
        deployments = [self._normalize_deployment(dep) for dep in payload]
        return {
            "repo": self.config.github_repo,
            "count": len(deployments),
            "deployments": deployments,
        }

    def get_deployment_status(self, deployment_id: int) -> dict[str, Any]:
        self._require_repo()
        payload = self._request_json(
            "GET",
            f"/repos/{self.config.github_repo}/deployments/{deployment_id}/statuses",
        )
        statuses = [
            {
                "state": status.get("state"),
                "description": status.get("description"),
                "created_at": status.get("created_at"),
            }
            for status in payload
        ]
        # GitHub returns statuses newest-first.
        latest_state = statuses[0]["state"] if statuses else "unknown"
        return {
            "deployment_id": deployment_id,
            "latest_state": latest_state,
            "statuses": statuses,
        }

    # ── Triggering workflows ─────────────────────────────────────────────

    def rerun_workflow(self, run_id: int, *, failed_jobs_only: bool = False) -> dict[str, Any]:
        """Re-run a workflow run. Mutating — only call this on an explicit request."""
        self._require_repo()
        suffix = "rerun-failed-jobs" if failed_jobs_only else "rerun"
        self._request_json(
            "POST", f"/repos/{self.config.github_repo}/actions/runs/{run_id}/{suffix}"
        )
        return {"run_id": run_id, "action": suffix, "triggered": True}

    def trigger_workflow(
        self, workflow: str, *, ref: str = "main", inputs: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Dispatch a workflow_dispatch event. Mutating — only call this on an explicit request."""
        self._require_repo()
        body: dict[str, Any] = {"ref": ref}
        if inputs:
            body["inputs"] = inputs
        self._request_json(
            "POST",
            f"/repos/{self.config.github_repo}/actions/workflows/{workflow}/dispatches",
            body=body,
        )
        return {"workflow": workflow, "ref": ref, "triggered": True}

    # ── GitHub Actions ───────────────────────────────────────────────────

    def list_workflow_runs(
        self, *, branch: str | None = None, status: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        self._require_repo()
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status
        payload = self._request_json(
            "GET",
            f"/repos/{self.config.github_repo}/actions/runs",
            params=params,
        )
        runs = [self._normalize_run(run) for run in payload.get("workflow_runs", [])]
        return {"repo": self.config.github_repo, "count": len(runs), "workflow_runs": runs}

    def summarize_ci(self, *, branch: str | None = None) -> dict[str, Any]:
        """Latest run per workflow, so you can see build/test/deploy health at a glance."""
        runs_payload = self.list_workflow_runs(branch=branch, limit=50)
        latest_by_workflow: dict[str, dict[str, Any]] = {}
        for run in runs_payload["workflow_runs"]:
            name = run["workflow_name"]
            if name not in latest_by_workflow:
                latest_by_workflow[name] = run
        return {
            "repo": self.config.github_repo,
            "branch": branch,
            "workflows": list(latest_by_workflow.values()),
        }

    # ── Question routing ─────────────────────────────────────────────────

    def ask(self, question: str) -> dict[str, Any]:
        """Best-effort natural-language entry point used by the orchestrator's /query contract.

        Raises CodeClientError when GitHub can't be queried, so /query returns a
        non-2xx status instead of an error message dressed up as an answer.
        """
        self._require_repo()
        q = question.lower()
        number_match = re.search(r"#?(\d+)", question)
        if number_match and ("pr" in q or "pull request" in q or "#" in question):
            number = int(number_match.group(1))
            status = self.get_pull_request_status(number)
            return {
                "answer": (
                    f"PR #{number} CI status: {status['overall']} "
                    f"({', '.join(f'{k}: {v}' for k, v in status['breakdown'].items()) or 'no check runs'})."
                ),
                "sources": [f"github:pull/{number}"],
                "data": status,
            }
        if "commit" in q:
            data = self.list_commits()
            lines = [f"{c['sha'][:7]} {c['message']}" for c in data["commits"][:5]]
            answer = (
                f"{data['count']} recent commit(s) — " + "; ".join(lines)
                if lines
                else "No commits found."
            )
            return {"answer": answer, "sources": ["github:commits"], "data": data}
        if "deploy" in q:
            data = self.list_deployments()
            lines = [f"{d['environment']}@{d['sha'][:7]}" for d in data["deployments"][:5]]
            answer = (
                f"{data['count']} recent deployment(s) — " + "; ".join(lines)
                if lines
                else "No deployments found."
            )
            return {"answer": answer, "sources": ["github:deployments"], "data": data}
        if "ci" in q or "pipeline" in q or "workflow" in q or "build" in q or "action" in q:
            summary = self.summarize_ci()
            lines = [
                f"{wf['workflow_name']}: {wf['conclusion'] or wf['status']}"
                for wf in summary["workflows"]
            ]
            answer = (
                "Latest workflow runs — " + "; ".join(lines)
                if lines
                else "No workflow runs found."
            )
            return {"answer": answer, "sources": ["github:actions/runs"], "data": summary}

        # default: open PR count
        pulls = self.list_pull_requests(state="open")
        answer = f"{pulls['count']} open pull request(s) on {pulls['repo']}."
        return {"answer": answer, "sources": ["github:pulls"], "data": pulls}

    # ── internals ─────────────────────────────────────────────────────────

    def _require_repo(self) -> None:
        if not self.config.github_repo:
            raise CodeClientError("GITHUB_REPO is not configured (expected 'owner/repo').", status_code=500)

    def _normalize_pr(self, pr: dict[str, Any], *, detailed: bool = False) -> dict[str, Any]:
        base = {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "state": pr.get("state"),
            "author": (pr.get("user") or {}).get("login"),
            "branch": (pr.get("head") or {}).get("ref"),
            "head_sha": (pr.get("head") or {}).get("sha"),
            "draft": pr.get("draft", False),
            "url": pr.get("html_url"),
        }
        if detailed:
            base["mergeable"] = pr.get("mergeable")
            base["merged"] = pr.get("merged", False)
        return base

    def _normalize_commit(self, commit: dict[str, Any], *, detailed: bool = False) -> dict[str, Any]:
        info = commit.get("commit", {})
        author = info.get("author") or {}
        base = {
            "sha": commit.get("sha"),
            "message": info.get("message", "").split("\n")[0],
            "author": author.get("name"),
            "date": author.get("date"),
            "url": commit.get("html_url"),
        }
        if detailed:
            stats = commit.get("stats", {})
            base["additions"] = stats.get("additions")
            base["deletions"] = stats.get("deletions")
            base["files_changed"] = len(commit.get("files", []))
        return base

    def _normalize_deployment(self, deployment: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": deployment.get("id"),
            "sha": deployment.get("sha"),
            "ref": deployment.get("ref"),
            "environment": deployment.get("environment"),
            "created_at": deployment.get("created_at"),
        }

    def _normalize_run(self, run: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": run.get("id"),
            "workflow_name": run.get("name"),
            "branch": run.get("head_branch"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "run_number": run.get("run_number"),
            "url": run.get("html_url"),
            "created_at": run.get("created_at"),
        }

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.config.github_api_base_url}{path}"
        if params:
            encoded = urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{encoded}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.config.github_token:
            headers["Authorization"] = f"Bearer {self.config.github_token}"

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore").strip()
            raise CodeClientError(
                f"{method} {url} failed with HTTP {exc.code}: {message or exc.reason}",
                status_code=_status_for_github_error(exc),
            ) from exc
        except URLError as exc:
            raise CodeClientError(f"Could not reach GitHub at {url}: {exc.reason}") from exc
        except TimeoutError as exc:  # read timeout: urlopen only wraps connect timeouts in URLError
            raise CodeClientError(
                f"GitHub did not respond within {self.config.timeout_seconds:g}s for {url}."
            ) from exc
        except json.JSONDecodeError as exc:
            raise CodeClientError(f"GitHub returned invalid JSON for {url}.") from exc


def _status_for_github_error(exc: HTTPError) -> int:
    """Map a GitHub HTTP error onto the status our own API returns."""
    if exc.code == 429 or (exc.code == 403 and exc.headers.get("x-ratelimit-remaining") == "0"):
        return 503  # rate limited — retry later
    if exc.code in (401, 403):
        return 500  # bad/missing token or no access to the repo — config problem
    if exc.code == 404:
        return 404  # PR / commit / run / workflow doesn't exist
    if 400 <= exc.code < 500:
        return 400  # e.g. 422 on an invalid workflow dispatch
    return 503  # GitHub 5xx
