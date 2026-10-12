begin;

-- A deployment administrator grants this capability to a dedicated server login.
-- It cannot read client application records and is never a Data API user role.
do $$ begin
    if not exists (select 1 from pg_roles where rolname = 'opsbrain_session_store') then
        create role opsbrain_session_store nologin;
    end if;
end $$;
grant usage on schema opsbrain_private to opsbrain_session_store;

create table opsbrain_private.app_sessions (
    session_hash text primary key check (session_hash ~ '^[a-f0-9]{64}$'),
    user_id uuid not null references auth.users(id) on delete cascade,
    token_ciphertext text not null check (octet_length(token_ciphertext) between 100 and 65536),
    token_expires_at bigint not null,
    expires_at bigint not null,
    last_seen_at bigint not null,
    check (expires_at > last_seen_at)
);
create index app_sessions_user_idx on opsbrain_private.app_sessions(user_id);
create index app_sessions_expiry_idx on opsbrain_private.app_sessions(expires_at);
alter table opsbrain_private.app_sessions enable row level security;
revoke all on opsbrain_private.app_sessions from public, anon, authenticated, service_role;
grant select, insert, update, delete on opsbrain_private.app_sessions to opsbrain_session_store;
create policy session_store_only on opsbrain_private.app_sessions to opsbrain_session_store
    using (true) with check (true);

commit;
