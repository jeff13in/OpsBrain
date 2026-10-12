"""Opaque sessions; production records live in a private PostgreSQL schema."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from cryptography.fernet import Fernet, InvalidToken


class InvalidIdentity(Exception):
    """The provider rejected this identity; never include provider bodies."""


class ProviderUnavailable(Exception):
    """Provider access failed safely; do not destroy a session on outages."""


@dataclass
class SessionRecord:
    session_hash: str
    user_id: str
    token_ciphertext: str = field(repr=False)
    token_expires_at: int
    expires_at: int
    last_seen_at: int


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_ids: tuple[str, ...]


class PostgresSessionStore:
    """Use a dedicated session-store login, never user-record CRUD credentials."""

    def __init__(self, dsn):
        self._dsn = dsn

    @contextmanager
    def locked(self, session_hash):
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self._dsn, connect_timeout=5, row_factory=dict_row) as conn:
            conn.execute("set local lock_timeout = '3s'")
            conn.execute("set local statement_timeout = '5s'")
            row = conn.execute(
                "select * from opsbrain_private.app_sessions where session_hash=%s for update",
                (session_hash,),
            ).fetchone()
            if row:
                row['user_id'] = str(row['user_id'])
            original = SessionRecord(**row) if row else None
            slot = [original]
            yield slot
            if original and slot[0] is None:
                conn.execute("delete from opsbrain_private.app_sessions where session_hash=%s", (session_hash,))
            elif slot[0] is not None:
                record = slot[0]
                conn.execute(
                    "update opsbrain_private.app_sessions set token_ciphertext=%s, token_expires_at=%s, "
                    "last_seen_at=%s where session_hash=%s",
                    (record.token_ciphertext, record.token_expires_at, record.last_seen_at, session_hash),
                )

    def insert(self, record):
        import psycopg

        with psycopg.connect(self._dsn, connect_timeout=5) as conn:
            conn.execute(
                "insert into opsbrain_private.app_sessions "
                "(session_hash,user_id,token_ciphertext,token_expires_at,expires_at,last_seen_at) "
                "values (%s,%s,%s,%s,%s,%s)",
                (record.session_hash, record.user_id, record.token_ciphertext, record.token_expires_at,
                 record.expires_at, record.last_seen_at),
            )


class SessionManager:
    """Provider and store are injected; no production in-memory fallback exists."""

    def __init__(self, store, provider, encryption_key, *, clock=time.time, absolute_seconds=604800, idle_seconds=86400):
        self.store, self.provider, self.clock = store, provider, clock
        self.cipher = Fernet(encryption_key)
        self.csrf_key = hashlib.sha256(b'opsbrain-csrf-v1\0' + base64.urlsafe_b64decode(encryption_key)).digest()
        self.absolute_seconds, self.idle_seconds = absolute_seconds, idle_seconds

    @staticmethod
    def cookie_hash(cookie):
        if not isinstance(cookie, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', cookie):
            return None
        return hashlib.sha256(cookie.encode()).hexdigest()

    def csrf_token(self, cookie):
        if self.cookie_hash(cookie) is None:
            raise InvalidIdentity()
        return base64.urlsafe_b64encode(hmac.digest(self.csrf_key, cookie.encode(), 'sha256')).decode().rstrip('=')

    def _encrypt(self, session_hash, access, refresh):
        return self.cipher.encrypt(json.dumps({'session_hash': session_hash, 'access': access, 'refresh': refresh}).encode()).decode()

    def _tokens(self, record):
        try:
            payload = json.loads(self.cipher.decrypt(record.token_ciphertext.encode()))
            if payload['session_hash'] != record.session_hash:
                raise InvalidIdentity()
            if not all(isinstance(payload[name], str) and payload[name] for name in ('access', 'refresh')):
                raise InvalidIdentity()
            return payload['access'], payload['refresh']
        except (InvalidToken, ValueError, KeyError, TypeError) as exc:
            raise InvalidIdentity() from exc

    def issue(self, access, refresh, expires_in):
        """Called only after a provider exchange, never with a browser user ID."""
        user_id = self.provider.verified_user(access)
        workspace_ids = tuple(self.provider.workspaces(access))
        if not workspace_ids or type(expires_in) is not int or not 0 < expires_in <= 86400:
            raise InvalidIdentity()
        now = int(self.clock())
        cookie = secrets.token_urlsafe(32)
        session_hash = self.cookie_hash(cookie)
        self.store.insert(SessionRecord(session_hash, user_id, self._encrypt(session_hash, access, refresh),
                                        now + expires_in, now + self.absolute_seconds, now))
        return cookie, Principal(user_id, workspace_ids)

    def authenticate(self, cookie):
        session_hash = self.cookie_hash(cookie)
        if session_hash is None:
            return None
        provider_failure = None
        principal = None
        with self.store.locked(session_hash) as slot:
            record = slot[0]
            now = int(self.clock())
            if record is None:
                return None
            if now >= record.expires_at or now - record.last_seen_at >= self.idle_seconds:
                slot[0] = None
                return None
            try:
                access, refresh = self._tokens(record)
                if now + 30 >= record.token_expires_at:
                    access, refresh, expires_in = self.provider.refresh(refresh)
                    if type(expires_in) is not int or not 0 < expires_in <= 86400:
                        raise InvalidIdentity()
                    record.token_ciphertext = self._encrypt(session_hash, access, refresh)
                    record.token_expires_at = now + expires_in
                user_id = self.provider.verified_user(access)
                workspace_ids = tuple(self.provider.workspaces(access))
                if user_id != record.user_id or not workspace_ids:
                    raise InvalidIdentity()
            except InvalidIdentity:
                slot[0] = None
                return None
            except ProviderUnavailable as exc:
                # Preserve a successful token rotation even if the subsequent
                # user/membership check fails; a rollback would lose the new pair.
                provider_failure = exc
            if provider_failure is None:
                # Validation/refresh must not extend the absolute lifetime.
                now = int(self.clock())
                if now >= record.expires_at or now - record.last_seen_at >= self.idle_seconds:
                    slot[0] = None
                    return None
                record.last_seen_at = now
                principal = Principal(user_id, workspace_ids)
        if provider_failure is not None:
            raise provider_failure
        return principal

    def logout(self, cookie):
        session_hash = self.cookie_hash(cookie)
        if session_hash is None:
            return
        access = None
        with self.store.locked(session_hash) as slot:
            if slot[0] is not None:
                try:
                    access, _ = self._tokens(slot[0])
                except InvalidIdentity:
                    pass
                slot[0] = None
        # Commit local revocation before asking the provider to revoke refresh.
        if access:
            try:
                self.provider.logout(access)
            except (InvalidIdentity, ProviderUnavailable):
                pass
