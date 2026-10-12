begin;
alter table public.profiles add column preferences jsonb not null default '{"default_section":"dashboard","reduced_motion":false}',
    add column version bigint not null default 1 check (version > 0),
    add column updated_at timestamptz not null default now();
alter table public.profiles add constraint preferences_shape check (
    jsonb_typeof(preferences)='object' and preferences - array['default_section','reduced_motion']='{}'::jsonb
    and preferences->>'default_section' in ('dashboard','projects','tools')
    and jsonb_typeof(preferences->'reduced_motion')='boolean'
    and preferences ?& array['default_section','reduced_motion']);
grant update (preferences) on public.profiles to authenticated;
grant insert (id) on public.projects to authenticated;
create trigger profiles_version before update on public.profiles for each row execute function opsbrain_private.bump_project_version();

create table public.saved_work (
    id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.workspaces(id) on delete cascade,
    project_id uuid not null, owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    title text not null check (char_length(btrim(title)) between 1 and 200),
    payload jsonb not null check (octet_length(payload::text)<=131072 and jsonb_typeof(payload)='object'
      and payload->>'mode'='demo' and payload - array['mode','turns']='{}'::jsonb and jsonb_typeof(payload->'turns')='array'
      and jsonb_array_length(payload->'turns') between 1 and 20 and payload ?& array['mode','turns']),
    version bigint not null default 1 check (version>0), created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
    foreign key (workspace_id,project_id) references public.projects(workspace_id,id) on delete cascade
);
create index saved_work_owner_idx on public.saved_work(workspace_id,owner_id,updated_at,id);
alter table public.saved_work enable row level security;
revoke all on public.saved_work from public,anon,authenticated;
grant select,delete on public.saved_work to authenticated;
grant insert (id,workspace_id,project_id,title,payload),update (title,payload) on public.saved_work to authenticated;
create policy saved_read on public.saved_work for select to authenticated using (owner_id=auth.uid() and opsbrain_private.owns_workspace(workspace_id));
create policy saved_insert on public.saved_work for insert to authenticated with check (owner_id=auth.uid() and opsbrain_private.owns_workspace(workspace_id));
create policy saved_update on public.saved_work for update to authenticated using (owner_id=auth.uid() and opsbrain_private.owns_workspace(workspace_id)) with check (owner_id=auth.uid() and opsbrain_private.owns_workspace(workspace_id));
create policy saved_delete on public.saved_work for delete to authenticated using (owner_id=auth.uid() and opsbrain_private.owns_workspace(workspace_id));
create trigger saved_version before update on public.saved_work for each row execute function opsbrain_private.bump_project_version();

create table public.workspace_tombstones (
    workspace_id uuid not null references public.workspaces(id) on delete cascade, record_id uuid not null,
    primary key(workspace_id,record_id)
);
create table public.workspace_receipts (
    workspace_id uuid not null references public.workspaces(id) on delete cascade, request_id uuid not null,
    fingerprint text not null check(fingerprint ~ '^[a-f0-9]{64}$'), result jsonb not null check(octet_length(result::text)<=1024),
    primary key(workspace_id,request_id)
);
alter table public.workspace_tombstones enable row level security;
alter table public.workspace_receipts enable row level security;
revoke all on public.workspace_tombstones,public.workspace_receipts from public,anon,authenticated;
grant select on public.workspace_tombstones,public.workspace_receipts to authenticated;
create policy tombstone_owner on public.workspace_tombstones to authenticated using (opsbrain_private.owns_workspace(workspace_id)) with check (opsbrain_private.owns_workspace(workspace_id));
create policy receipt_owner on public.workspace_receipts to authenticated using (opsbrain_private.owns_workspace(workspace_id)) with check (opsbrain_private.owns_workspace(workspace_id));

create function opsbrain_private.persistence_insert_guard() returns trigger language plpgsql set search_path='' as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(new.workspace_id::text,0));
    if exists(select 1 from public.workspace_tombstones where workspace_id=new.workspace_id and record_id=new.id) then
        raise exception 'Record deleted' using errcode='P0002';
    end if;
    if tg_table_name='projects' and (select count(*) from public.projects where workspace_id=new.workspace_id)>=100 then
        raise exception 'Project limit reached' using errcode='54000';
    elsif tg_table_name='saved_work' and (select count(*) from public.saved_work where workspace_id=new.workspace_id)>=100 then
        raise exception 'Saved work limit reached' using errcode='54000';
    end if;
    return new;
end $$;
create function opsbrain_private.persistence_delete_guard() returns trigger language plpgsql security definer set search_path='' as $$
begin
    if exists(select 1 from public.workspaces where id=old.workspace_id) then
        insert into public.workspace_tombstones values(old.workspace_id,old.id) on conflict do nothing;
    end if;
    return old;
end $$;
revoke all on function opsbrain_private.persistence_insert_guard(),opsbrain_private.persistence_delete_guard() from public,anon,authenticated;
create trigger project_insert_guard before insert on public.projects for each row execute function opsbrain_private.persistence_insert_guard();
create trigger saved_insert_guard before insert on public.saved_work for each row execute function opsbrain_private.persistence_insert_guard();
create trigger project_delete_guard after delete on public.projects for each row execute function opsbrain_private.persistence_delete_guard();
create trigger saved_delete_guard after delete on public.saved_work for each row execute function opsbrain_private.persistence_delete_guard();

create function opsbrain_private.receipt_limit() returns trigger language plpgsql set search_path='' as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(new.workspace_id::text,0));
    if new.result->>'deleted'<>'true' and (select count(*) from public.workspace_receipts where workspace_id=new.workspace_id)>=5000 then raise exception 'Request limit reached' using errcode='54000'; end if;
    return new;
end $$;
revoke all on function opsbrain_private.receipt_limit() from public,anon,authenticated;
create trigger receipt_limit before insert on public.workspace_receipts for each row execute function opsbrain_private.receipt_limit();

-- Narrow metadata helper only; ordinary record CRUD above/below still uses RLS.
-- Never expose the private schema through the Data API.
create function opsbrain_private.store_receipt(ws uuid,key uuid,fingerprint text,result jsonb)
returns void language plpgsql security definer set search_path='' as $$
begin
    if not opsbrain_private.owns_workspace(ws) then raise exception 'Workspace denied' using errcode='42501'; end if;
    insert into public.workspace_receipts values(ws,key,fingerprint,result);
end $$;
revoke all on function opsbrain_private.store_receipt(uuid,uuid,text,jsonb) from public,anon;
grant execute on function opsbrain_private.store_receipt(uuid,uuid,text,jsonb) to authenticated;

create function public.workspace_mutate(request_id uuid,target_workspace uuid,operation text,record_id uuid,expected_version bigint,changes jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare fingerprint text; receipt public.workspace_receipts; result jsonb; current_version bigint;
begin
    if not opsbrain_private.owns_workspace(target_workspace) then raise exception 'Workspace denied' using errcode='42501'; end if;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(target_workspace::text,0));
    fingerprint:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(pg_catalog.jsonb_build_array(operation,record_id,expected_version,changes)::text,'utf8')),'hex');
    if operation not like '%.delete' and exists(select 1 from public.workspace_tombstones t where t.workspace_id=target_workspace and t.record_id=workspace_mutate.record_id) then
        raise exception 'Record deleted' using errcode='P0002';
    end if;
    select * into receipt from public.workspace_receipts r where r.workspace_id=target_workspace and r.request_id=workspace_mutate.request_id;
    if found then
        if receipt.fingerprint<>fingerprint then raise exception 'Retry payload changed' using errcode='40001'; end if;
        return receipt.result;
    end if;
    if operation not like '%.delete' and (select count(*) from public.workspace_receipts where workspace_id=target_workspace)>=5000 then raise exception 'Request limit reached' using errcode='54000'; end if;
    if operation='project.create' and expected_version=0 then
        insert into public.projects(id,workspace_id,title) values(record_id,target_workspace,changes->>'title') returning version into current_version;
    elsif operation='saved.create' and expected_version=0 then
        insert into public.saved_work(id,workspace_id,project_id,title,payload) values(record_id,target_workspace,(changes->>'project_id')::uuid,changes->>'title',changes->'payload') returning version into current_version;
    elsif operation='profile.update' and record_id=auth.uid() then
        update public.profiles set display_name=changes->>'display_name',preferences=changes->'preferences' where user_id=auth.uid() and version=expected_version returning version into current_version;
    elsif operation='project.update' then
        update public.projects set title=changes->>'title' where id=record_id and workspace_id=target_workspace and version=expected_version returning version into current_version;
    elsif operation='saved.update' then
        update public.saved_work set title=changes->>'title',payload=changes->'payload' where id=record_id and workspace_id=target_workspace and version=expected_version returning version into current_version;
    elsif operation='project.delete' then
        delete from public.projects where id=record_id and workspace_id=target_workspace and version=expected_version returning version into current_version;
    elsif operation='saved.delete' then
        delete from public.saved_work where id=record_id and workspace_id=target_workspace and version=expected_version returning version into current_version;
    else raise exception 'Invalid operation' using errcode='22023'; end if;
    if current_version is null then raise exception 'Version conflict or unavailable record' using errcode='40001'; end if;
    result:=pg_catalog.jsonb_build_object('id',record_id,'version',current_version,'deleted',operation like '%.delete');
    perform opsbrain_private.store_receipt(target_workspace,request_id,fingerprint,result);
    return result;
end $$;
revoke all on function public.workspace_mutate(uuid,uuid,text,uuid,bigint,jsonb) from public,anon;
grant execute on function public.workspace_mutate(uuid,uuid,text,uuid,bigint,jsonb) to authenticated;
commit;
