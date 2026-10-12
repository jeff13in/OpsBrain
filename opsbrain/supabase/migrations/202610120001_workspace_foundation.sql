-- Application records only: do not apply to the operational pgvector database.
begin;

create schema if not exists opsbrain_private;
revoke all on schema opsbrain_private from public, anon, authenticated;
grant usage on schema opsbrain_private to authenticated, service_role;

create table opsbrain_private.beta_approvals (
    user_id uuid primary key references auth.users(id) on delete cascade,
    approved_at timestamptz not null default now()
);
alter table opsbrain_private.beta_approvals enable row level security;
revoke all on opsbrain_private.beta_approvals from public, anon, authenticated;
grant select, insert, delete on opsbrain_private.beta_approvals to service_role;

create table public.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    display_name text not null default '' check (char_length(display_name) <= 120),
    created_at timestamptz not null default now()
);

create table public.workspaces (
    id uuid primary key default gen_random_uuid(),
    personal_owner_id uuid not null unique references auth.users(id) on delete cascade,
    name text not null check (char_length(btrim(name)) between 1 and 120),
    created_at timestamptz not null default now()
);

create table public.workspace_members (
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null default 'owner' check (role = 'owner'),
    primary key (workspace_id, user_id)
);
create index workspace_members_user_idx on public.workspace_members(user_id, workspace_id);

create table public.projects (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    creator_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    title text not null check (char_length(btrim(title)) between 1 and 200),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version bigint not null default 1 check (version > 0),
    unique (workspace_id, id)
);
create index projects_workspace_idx on public.projects(workspace_id, created_at, id);

-- Helpers read privileged tables, but derive identity only from auth.uid().
-- The private schema must never be configured as a Data API exposed schema.
create function opsbrain_private.is_approved_user()
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from opsbrain_private.beta_approvals a
        join auth.users u on u.id = a.user_id
        where a.user_id = (select auth.uid()) and u.email_confirmed_at is not null
    );
$$;

create function opsbrain_private.owns_workspace(target_workspace uuid)
returns boolean language sql stable security definer set search_path = '' as $$
    select opsbrain_private.is_approved_user() and exists (
        select 1 from public.workspace_members m
        join public.workspaces w on w.id = m.workspace_id
        where m.workspace_id = target_workspace and m.user_id = (select auth.uid())
          and m.role = 'owner' and w.personal_owner_id = (select auth.uid())
    );
$$;
revoke all on function opsbrain_private.is_approved_user() from public, anon, authenticated;
revoke all on function opsbrain_private.owns_workspace(uuid) from public, anon, authenticated;
grant execute on function opsbrain_private.is_approved_user() to authenticated;
grant execute on function opsbrain_private.owns_workspace(uuid) to authenticated;

alter table public.profiles enable row level security;
alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.projects enable row level security;
-- Supabase projects may grant table access by default: remove inherited grants.
revoke all on public.profiles, public.workspaces, public.workspace_members, public.projects
    from public, anon, authenticated;
grant select on public.profiles, public.workspaces, public.workspace_members, public.projects to authenticated;
grant update (display_name) on public.profiles to authenticated;
grant update (name) on public.workspaces to authenticated;
grant insert (workspace_id, title), update (title), delete on public.projects to authenticated;

create policy profiles_read on public.profiles for select to authenticated
    using (user_id = (select auth.uid()) and opsbrain_private.is_approved_user());
create policy profiles_update on public.profiles for update to authenticated
    using (user_id = (select auth.uid()) and opsbrain_private.is_approved_user())
    with check (user_id = (select auth.uid()) and opsbrain_private.is_approved_user());
create policy workspaces_read on public.workspaces for select to authenticated
    using (opsbrain_private.owns_workspace(id));
create policy workspaces_update on public.workspaces for update to authenticated
    using (opsbrain_private.owns_workspace(id)) with check (opsbrain_private.owns_workspace(id));
create policy members_read on public.workspace_members for select to authenticated
    using (user_id = (select auth.uid()) and opsbrain_private.owns_workspace(workspace_id));
create policy projects_read on public.projects for select to authenticated
    using (opsbrain_private.owns_workspace(workspace_id));
create policy projects_insert on public.projects for insert to authenticated
    with check (creator_id = (select auth.uid()) and opsbrain_private.owns_workspace(workspace_id));
create policy projects_update on public.projects for update to authenticated
    using (opsbrain_private.owns_workspace(workspace_id))
    with check (creator_id = (select auth.uid()) and opsbrain_private.owns_workspace(workspace_id));
create policy projects_delete on public.projects for delete to authenticated
    using (opsbrain_private.owns_workspace(workspace_id));

create function opsbrain_private.bump_project_version()
returns trigger language plpgsql set search_path = '' as $$
begin
    new.version := old.version + 1;
    new.updated_at := pg_catalog.clock_timestamp();
    return new;
end;
$$;
revoke all on function opsbrain_private.bump_project_version() from public, anon, authenticated;
create trigger projects_version before update on public.projects
    for each row execute function opsbrain_private.bump_project_version();

-- Only the backend's narrow administrative bootstrap path may call this RPC.
-- Normal project/profile CRUD must use a user JWT and RLS, not service_role.
create function public.provision_personal_workspace(target_user uuid)
returns uuid language plpgsql security definer set search_path = '' as $$
declare workspace_uuid uuid;
begin
    if not exists (
        select 1 from auth.users u join opsbrain_private.beta_approvals a on a.user_id = u.id
        where u.id = target_user and u.email_confirmed_at is not null
    ) then
        raise exception 'Verified approved identity required' using errcode = '42501';
    end if;
    insert into public.profiles (user_id) values (target_user) on conflict (user_id) do nothing;
    insert into public.workspaces (personal_owner_id, name) values (target_user, 'Personal workspace')
        on conflict (personal_owner_id) do update set personal_owner_id = excluded.personal_owner_id
        returning id into workspace_uuid;
    insert into public.workspace_members (workspace_id, user_id) values (workspace_uuid, target_user)
        on conflict (workspace_id, user_id) do nothing;
    return workspace_uuid;
end;
$$;
revoke all on function public.provision_personal_workspace(uuid) from public, anon, authenticated;
grant execute on function public.provision_personal_workspace(uuid) to service_role;

commit;
