"""Live deployed monitoring + RAG fan-out/synthesis and metrics smoke test.

Does not simulate agents or alter transport; use the Compose override separately.
Answers may consume provider quota. Output never contains environment secrets.
"""
import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from shared.models import AskResponse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["http", "kafka"], required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checks = []
    with httpx.Client(timeout=120) as client:
        for port in range(8000, 8005):
            try:
                response = client.get(f"http://localhost:{port}/metrics")
                valid = response.status_code == 200 and "opsbrain_http_requests" in response.text
                checks.append({"name": "metrics", "port": port, "status": "passed" if valid else "failed"})
            except (httpx.HTTPError, ValueError) as exc:
                checks.append({"name": "metrics", "port": port, "status": "failed", "error_type": type(exc).__name__})
        for question, agents in [
            ("Are any alerts firing?", ["monitoring"]),
            ("Check firing alerts and explain the documented troubleshooting procedure.", ["rag", "monitoring"]),
        ]:
            started = time.monotonic()
            try:
                response = client.post("http://localhost:8000/ask", json={"question": question})
                body = AskResponse.model_validate(response.json())
                valid = response.status_code == 200 and body.status == "ok" and set(body.routing.agents) == set(agents)
                valid = valid and body.routing.method == "llm"
                if len(agents) > 1:
                    valid = valid and not body.answer.startswith("[rag]")
                    valid = valid and all(f"[{source}]" in body.answer for source in body.sources)
                checks.append({"name": "ask", "question": question, "expected_agents": agents,
                               "status": "passed" if valid else "failed", "seconds": round(time.monotonic() - started, 3),
                               "response": body.model_dump(mode="json")})
            except (httpx.HTTPError, ValueError) as exc:
                checks.append({"name": "ask", "question": question, "status": "failed", "error_type": type(exc).__name__})
    report = {"timestamp": datetime.now(UTC).isoformat(), "mode": "live-services-and-providers",
              "transport": args.transport, "note": "Transport selected externally in Compose; no simulated backend summaries.",
              "checks": checks}
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for check in checks:
        print(f"{check['status']}: {check['name']}")
    return int(any(check["status"] != "passed" for check in checks))


if __name__ == "__main__":
    raise SystemExit(main())
