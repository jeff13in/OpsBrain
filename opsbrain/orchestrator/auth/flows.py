"""Durable anonymous/recovery contexts and atomic cross-replica auth limits."""

import base64
import hashlib
import hmac
import secrets
import time
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from orchestrator.auth.sessions import (
    InvalidIdentity,
    ProviderUnavailable,
    SessionManager,
)


class Throttled(ProviderUnavailable):
    def __init__(self, retry_after=60):
        self.retry_after = retry_after


class PostgresAuthStore:
    def __init__(self, dsn):
        self._dsn = dsn

    @contextmanager
    def connection(self):
        with psycopg.connect(self._dsn, connect_timeout=5, row_factory=dict_row) as conn:
            conn.execute("set local lock_timeout='3s'")
            conn.execute("set local statement_timeout='5s'")
            yield conn

    def invited(self, email):
        email_hash = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        with self.connection() as conn:
            return conn.execute('select 1 from opsbrain_private.beta_invites where email_hash=%s', (email_hash,)).fetchone() is not None

    def put(self, key, user, ciphertext, expires):
        with self.connection() as conn:
            conn.execute('insert into opsbrain_private.auth_flows values (%s,%s,%s,%s)', (key, user, ciphertext, expires))

    def get(self, key, now, *, consume=False):
        with self.connection() as conn:
            if consume:
                return conn.execute('delete from opsbrain_private.auth_flows where flow_hash=%s and expires_at>%s returning *', (key, now)).fetchone()
            return conn.execute('select * from opsbrain_private.auth_flows where flow_hash=%s and expires_at>%s', (key, now)).fetchone()

    def delete(self, key):
        with self.connection() as conn:
            conn.execute('delete from opsbrain_private.auth_flows where flow_hash=%s', (key,))

    def revoke_user(self, user):
        # Dedicated login needs both auth and session capabilities. No public CRUD.
        with self.connection() as conn:
            conn.execute('delete from opsbrain_private.app_sessions where user_id=%s', (user,))
            conn.execute('delete from opsbrain_private.auth_flows where user_id=%s', (user,))

    def put_oauth(self, key, verifier, expires):
        with self.connection() as conn:
            conn.execute('insert into opsbrain_private.oauth_states values (%s,%s,%s)', (key, verifier, expires))

    def take_oauth(self, key, now):
        # Consumed even when expired: a verifier is never usable twice.
        with self.connection() as conn:
            row = conn.execute('delete from opsbrain_private.oauth_states where state_hash=%s returning *', (key,)).fetchone()
        return row['code_verifier'] if row and row['expires_at'] > now else None

    def rate(self, key, now, window, limit):
        start = now // window * window
        with self.connection() as conn:
            row = conn.execute('''insert into opsbrain_private.auth_rate_limits values (%s,%s,1)
                on conflict (bucket_hash) do update set window_start=excluded.window_start,
                attempts=case when auth_rate_limits.window_start=excluded.window_start
                    then least(auth_rate_limits.attempts+1,1000) else 1 end returning attempts''', (key, start)).fetchone()
        return row['attempts'] <= limit

    def cleanup(self, now):
        with self.connection() as conn:
            conn.execute('delete from opsbrain_private.auth_flows where expires_at<=%s', (now,))
            conn.execute('delete from opsbrain_private.oauth_states where expires_at<=%s', (now,))
            conn.execute('delete from opsbrain_private.auth_rate_limits where window_start<%s', (now - 86400,))
            conn.execute('delete from opsbrain_private.app_sessions where expires_at<=%s or last_seen_at<=%s', (now, now - 86400))


class AccountFlows:
    def __init__(self, store, manager, *, clock=time.time):
        self.store, self.manager, self.clock = store, manager, clock

    def csrf(self, cookie):
        if SessionManager.cookie_hash(cookie) is None:
            raise InvalidIdentity()
        return hmac.digest(self.manager.csrf_key, b'auth-flow\0' + cookie.encode(), 'sha256').hex()

    def context(self, cookie, *, consume=False):
        key = SessionManager.cookie_hash(cookie)
        return self.store.get(key, int(self.clock()), consume=consume) if key else None

    def issue(self, tokens=None):
        cookie = secrets.token_urlsafe(32)
        key = SessionManager.cookie_hash(cookie)
        user, cipher, expires = None, None, int(self.clock()) + 3600
        if tokens:
            access, refresh, expires_in = tokens
            user = self.manager.provider.verified_user(access)
            expires = int(self.clock()) + min(expires_in, 900)
            cipher = self.manager._encrypt(key, access, refresh)
        self.store.put(key, user, cipher, expires)
        return cookie

    def begin_oauth(self):
        """Return (browser state cookie, S256 challenge); only the cookie hash is stored."""
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        self.store.put_oauth(SessionManager.cookie_hash(state), verifier, int(self.clock()) + 600)
        return state, challenge

    def take_oauth(self, cookie):
        key = SessionManager.cookie_hash(cookie)
        return self.store.take_oauth(key, int(self.clock())) if key else None

    def limit(self, ip, action, email=None):
        rules = [('global:' + action, 60, 100), ('ip:' + ip + ':' + action, 60, 20)]
        if email:
            rules.append(('email:' + email.lower(), 900, 5))
        for bucket, window, limit in rules:
            key = hmac.digest(self.manager.csrf_key, bucket.encode(), 'sha256').hex()
            if not self.store.rate(key, int(self.clock()), window, limit):
                raise Throttled(window - int(self.clock()) % window)
