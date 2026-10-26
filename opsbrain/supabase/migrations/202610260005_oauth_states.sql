begin;

-- One-time PKCE verifiers for server-side Google sign-in. A row is keyed by the
-- SHA-256 of an HttpOnly browser cookie and consumed by the callback exchange.
create table opsbrain_private.oauth_states (
    state_hash text primary key check (state_hash ~ '^[a-f0-9]{64}$'),
    code_verifier text not null check (code_verifier ~ '^[A-Za-z0-9_-]{43,128}$'),
    expires_at bigint not null
);
create index oauth_states_expiry_idx on opsbrain_private.oauth_states(expires_at);
alter table opsbrain_private.oauth_states enable row level security;
revoke all on opsbrain_private.oauth_states from public, anon, authenticated, service_role;
grant select, insert, delete on opsbrain_private.oauth_states to opsbrain_auth_store;
create policy oauth_states_server on opsbrain_private.oauth_states
    to opsbrain_auth_store using (true) with check (true);
commit;
