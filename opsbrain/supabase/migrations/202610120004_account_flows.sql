begin;

-- Administrator-managed approved-beta addresses; never exposed by Data API.
create table opsbrain_private.beta_invites (
    email_hash text primary key check (email_hash ~ '^[a-f0-9]{64}$'),
    created_at timestamptz not null default now()
);
create table opsbrain_private.auth_flows (
    flow_hash text primary key check (flow_hash ~ '^[a-f0-9]{64}$'),
    user_id uuid references auth.users(id) on delete cascade,
    token_ciphertext text,
    expires_at bigint not null,
    check ((user_id is null and token_ciphertext is null) or
           (user_id is not null and octet_length(token_ciphertext) between 100 and 65536))
);
create index auth_flows_expiry_idx on opsbrain_private.auth_flows(expires_at);
create table opsbrain_private.auth_rate_limits (
    bucket_hash text primary key check (bucket_hash ~ '^[a-f0-9]{64}$'),
    window_start bigint not null,
    attempts integer not null check (attempts between 1 and 1000)
);
do $$ begin
    if not exists (select 1 from pg_roles where rolname = 'opsbrain_auth_store') then
        create role opsbrain_auth_store nologin;
    end if;
end $$;
grant usage on schema opsbrain_private to opsbrain_auth_store;

-- JWTs can remain valid after provider bans: enforce current identity state
-- at the database boundary as well as in backend provider revalidation.
create or replace function opsbrain_private.is_approved_user()
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from opsbrain_private.beta_approvals a
        join auth.users u on u.id = a.user_id
        where a.user_id = (select auth.uid()) and u.email_confirmed_at is not null
          and not coalesce(u.is_anonymous, false) and u.deleted_at is null
          and (u.banned_until is null or u.banned_until <= pg_catalog.now())
    );
$$;
alter table opsbrain_private.beta_invites enable row level security;
alter table opsbrain_private.auth_flows enable row level security;
alter table opsbrain_private.auth_rate_limits enable row level security;
revoke all on opsbrain_private.beta_invites, opsbrain_private.auth_flows,
    opsbrain_private.auth_rate_limits from public, anon, authenticated, service_role;
grant select on opsbrain_private.beta_invites to opsbrain_auth_store;
grant select, insert, update, delete on opsbrain_private.auth_flows,
    opsbrain_private.auth_rate_limits to opsbrain_auth_store;
create policy auth_invites_read on opsbrain_private.beta_invites for select
    to opsbrain_auth_store using (true);
create policy auth_flows_server on opsbrain_private.auth_flows
    to opsbrain_auth_store using (true) with check (true);
create policy auth_limits_server on opsbrain_private.auth_rate_limits
    to opsbrain_auth_store using (true) with check (true);

-- User JWT verifies identity; this narrow definer creates only that user's
-- approved personal workspace. No service key is needed during login/callback.
create function public.ensure_personal_workspace()
returns uuid language plpgsql security definer set search_path = '' as $$
declare target uuid := auth.uid(); address text;
begin
    select u.email into address from auth.users u
        where u.id = target and u.email_confirmed_at is not null
          and not coalesce(u.is_anonymous, false) and u.deleted_at is null
          and (u.banned_until is null or u.banned_until <= pg_catalog.now());
    if address is null then
        raise exception 'Verified approved identity required' using errcode = '42501';
    end if;
    if exists (select 1 from opsbrain_private.beta_invites i where i.email_hash =
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(pg_catalog.lower(pg_catalog.btrim(address)), 'UTF8')), 'hex')) then
        insert into opsbrain_private.beta_approvals(user_id) values (target)
            on conflict (user_id) do nothing;
    end if;
    return public.provision_personal_workspace(target);
end;
$$;
revoke all on function public.ensure_personal_workspace() from public, anon, authenticated;
grant execute on function public.ensure_personal_workspace() to authenticated;
commit;
