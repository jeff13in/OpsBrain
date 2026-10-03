"""Conversation memory for the Orchestrator (OPU-43).

In-process and per-replica: a session's history lives only in the pod that
served it. Fine for local/compose and a single replica; with k8s replicas > 1
it needs sticky sessions or a shared store (Postgres/Redis) — tracked as a
known gap in CONTRACT.md.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock

MAX_TURNS = 6            # user+assistant pairs kept per session
MAX_SESSIONS = 1000      # least-recently-used sessions are evicted past this
SESSION_TTL_S = 60 * 60  # sessions idle for an hour are forgotten


class SessionMemory:
    def __init__(self, max_turns: int = MAX_TURNS, max_sessions: int = MAX_SESSIONS, ttl_s: float = SESSION_TTL_S) -> None:
        self.max_turns = max_turns
        self.max_sessions = max_sessions
        self.ttl_s = ttl_s
        self._sessions: OrderedDict[str, tuple[float, list[dict[str, str]]]] = OrderedDict()
        self._lock = Lock()

    def history(self, session_id: str | None) -> list[dict[str, str]]:
        if not session_id:
            return []
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None or time.monotonic() - entry[0] > self.ttl_s:
                self._sessions.pop(session_id, None)
                return []
            return list(entry[1])

    def append(self, session_id: str | None, question: str, answer: str) -> None:
        if not session_id:
            return
        with self._lock:
            _, turns = self._sessions.pop(session_id, (0.0, []))
            turns = [*turns, {"role": "user", "content": question}, {"role": "assistant", "content": answer}]
            self._sessions[session_id] = (time.monotonic(), turns[-2 * self.max_turns:])
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
