"""Validate the running local RAG API and persisted vectors using real services.

Run from the repo root: python -m scripts.validate_rag
Requires DATABASE_URL, a running RAG API, GOOGLE_API_KEY for embeddings,
and LLM_API_KEY for Groq chat (or the configured Ollama endpoint).
Reingests the selected directory twice (replacing its existing source chunks).
"""

import argparse
import json
import sys
from collections import Counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg
from psycopg import sql
from rag.ingestor import build_chunks
from rag.retriever import RetrieverConfig


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def request(base_url, path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(base_url + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as response:
            return json.load(response)
    except HTTPError as exc:
        # Avoid printing provider errors or credentials returned by dependencies.
        raise RuntimeError(f"{path} returned HTTP {exc.code}; check the RAG service logs.") from None


def stored_chunks(config, sources):
    with psycopg.connect(config.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "SELECT source, content, metadata->>'chunk_index', "
                    "vector_dims(embedding), vector_norm(embedding) "
                    "FROM {} WHERE source = ANY(%s)"
                ).format(sql.Identifier(config.documents_table)),
                (sources,),
            )
            return cursor.fetchall()


def validate(args):
    config = RetrieverConfig()
    chunks = build_chunks(args.directory)
    require(bool(chunks), "No supported runbooks found in the local directory.")
    sources = sorted({chunk.source for chunk in chunks})
    expected = Counter((c.source, c.content, str(c.chunk_index)) for c in chunks)
    require(args.expected_source in sources, "Expected source is missing from the runbooks.")
    require(request(args.base_url, "/health").get("status") == "ok", "Health check failed.")
    print("PASS: RAG API health")

    for attempt in (1, 2):
        result = request(args.base_url, "/ingest", {"directory": args.api_directory})
        require(result.get("documents_processed") == len(sources), "Unexpected document count.")
        require(result.get("chunks_stored") == len(chunks), "Unexpected chunk count.")
        rows = stored_chunks(config, sources)
        require(Counter(row[:3] for row in rows) == expected, "Persisted chunks differ or are duplicated.")
        require(all(row[3] == 3072 and row[4] > 0 for row in rows), "Invalid stored embeddings.")
        print(f"PASS: ingestion {attempt}: {len(sources)} documents, {len(rows)} nonzero 3072-dimension vectors")

    result = request(args.base_url, "/query", {"question": args.question, "top_k": 4})
    require(result.get("grounded") is True, "Response is ungrounded.")
    require(result.get("validation_errors") == [], "Response has validation errors.")
    require(0 < result.get("retrieved_chunks", 0) <= 4, "Unexpected retrieval count.")
    returned_sources = result.get("sources", [])
    require(args.expected_source in returned_sources, "Expected runbook was not retrieved.")
    require(set(returned_sources) <= set(sources), "Response contains unexpected sources.")
    answer = result.get("answer", "").strip()
    require(bool(answer), "Response is empty.")
    require(f"[{args.expected_source}]" in answer, "Expected runbook citation is missing.")
    print(f"PASS: query: {result['retrieved_chunks']} chunks, grounded answer with expected citation")
    print(json.dumps(result, indent=2, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--directory", default="/app/data", help="Runbooks visible to this script")
    parser.add_argument("--api-directory", default="/app/data", help="Same runbooks visible to the API")
    parser.add_argument("--question", default="What should I do when CPU usage is high?")
    parser.add_argument("--expected-source", default="runbook-high-cpu.md")
    args = parser.parse_args()
    args.base_url = args.base_url.rstrip("/")
    try:
        validate(args)
    except Exception as exc:
        # Database/provider exceptions can contain connection credentials.
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(f"FAIL: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
