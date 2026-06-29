-- Clean baseline schema for fresh Supabase environments.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- Application user profiles. Auth credentials live in auth.users; business
-- role/status state lives here.
create table if not exists public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  username text,
  nickname text,
  role text not null default 'user'
    check (role in ('admin','user')),
  status text not null default 'active'
    check (status in ('active','disabled')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- WeChat official account groups.
create table if not exists public.wechat_account_groups (
  id serial primary key,
  name text not null unique,
  description text,
  cover text,
  status integer not null default 1,
  schedule_enabled boolean not null default false,
  schedule_time time,
  collection_pages integer not null default 1
    check (collection_pages between 1 and 5),
  last_scheduled_date date,
  last_scheduled_at timestamptz,
  last_collection_run_id uuid,
  last_schedule_error text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (not schedule_enabled or schedule_time is not null)
);

-- WeChat official account subscription sources.
create table if not exists public.wechat_accounts (
  id text primary key,
  name text not null,
  description text,
  logo_url text,
  faker_id text not null unique,
  group_id integer references public.wechat_account_groups(id) on delete set null,
  last_publish timestamptz,
  last_fetch timestamptz,
  status integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Collected articles. These are shared system data, not per-user crawl results.
create table if not exists public.articles (
  id text primary key,
  wechat_account_id text references public.wechat_accounts(id) on delete cascade,
  title text not null,
  description text,
  pic_url text,
  content text,
  content_md text,
  content_fetch_status text not null default 'pending'
    check (content_fetch_status in ('pending','fetched','failed','fallback_required')),
  content_fetch_error text,
  activity_extraction_status text not null default 'pending'
    check (activity_extraction_status in ('pending','processing','extracted','not_activity','failed','fallback_required')),
  activity_extraction_error text,
  publish_time bigint,
  url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Article image mappings for the Supabase Storage bucket: article-images.
create table if not exists public.article_images (
  id uuid primary key default gen_random_uuid(),
  article_id text not null references public.articles(id) on delete cascade,
  bucket text not null default 'article-images',
  object_path text not null,
  public_url text not null default '',
  origin_url text not null default '',
  position integer not null default 1,
  ocr_status text not null default 'pending'
    check (ocr_status in ('pending', 'completed', 'failed')),
  ocr_text text not null default '',
  ocr_confidence double precision,
  ocr_provider text not null default '',
  ocr_error text not null default '',
  ocr_finished_at timestamptz,
  created_at timestamptz not null default now(),
  unique (article_id, object_path)
);

-- Article collection tasks. A run represents a manual account/group sync request;
-- items are queued per WeChat account so workers can process them serially.
create table if not exists public.article_collection_runs (
  id uuid primary key default gen_random_uuid(),
  scope text not null
    check (scope in ('single_account','group')),
  group_id integer references public.wechat_account_groups(id) on delete set null,
  status text not null default 'queued'
    check (status in ('queued','processing','success','partial_success','failed','canceled')),
  start_page integer not null default 0,
  max_page integer not null default 1,
  total_items integer not null default 0,
  success_items integer not null default 0,
  failed_items integer not null default 0,
  skipped_items integer not null default 0,
  articles_count integer not null default 0,
  error text not null default '',
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.wechat_account_groups
  add constraint wechat_account_groups_last_collection_run_id_fkey
  foreign key (last_collection_run_id)
  references public.article_collection_runs(id)
  on delete set null;

create table if not exists public.article_collection_items (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.article_collection_runs(id) on delete cascade,
  wechat_account_id text not null references public.wechat_accounts(id) on delete cascade,
  account_snapshot jsonb not null default '{}'::jsonb,
  status text not null default 'queued'
    check (status in ('queued','processing','success','failed','skipped','canceled')),
  start_page integer not null default 0,
  max_page integer not null default 1,
  articles_count integer not null default 0,
  error text not null default '',
  queued_at timestamptz not null default now(),
  locked_at timestamptz,
  locked_by text,
  attempt_count integer not null default 0,
  max_attempts integer not null default 1,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (run_id, wechat_account_id)
);

-- Internal audit records for activity extraction attempts.
create table if not exists public.activity_extraction_runs (
  id uuid primary key default gen_random_uuid(),
  article_id text not null references public.articles(id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued','processing','success','not_activity','failed','fallback_required')),
  model text not null default '',
  prompt_version text not null default 'activity_extraction.v1',
  input_snapshot jsonb not null default '{}'::jsonb,
  raw_output jsonb not null default '{}'::jsonb,
  raw_output_text text not null default '',
  error text not null default '',
  queued_at timestamptz not null default now(),
  locked_at timestamptz,
  locked_by text,
  attempt_count integer not null default 0,
  max_attempts integer not null default 1,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Product activities extracted from articles.
create table if not exists public.activities (
  id uuid primary key default gen_random_uuid(),
  article_id text not null references public.articles(id) on delete cascade,
  extraction_run_id uuid references public.activity_extraction_runs(id) on delete set null,
  source_wechat_account_id text references public.wechat_accounts(id) on delete set null,
  title text not null default '',
  article_url text not null default '',
  summary text not null default '',
  event_time_text text not null default '',
  start_at timestamptz,
  end_at timestamptz,
  event_status text not null default 'unknown'
    check (event_status in ('upcoming','ongoing','ended','unknown')),
  location_text text not null default '',
  registration_text text not null default '',
  registration_method text not null default 'unknown'
    check (registration_method in ('qr_code','link','phone','wechat','onsite','none','unknown')),
  registration_url text not null default '',
  qr_image_urls jsonb not null default '[]'::jsonb,
  fee_text text not null default '',
  audience text not null default '',
  review_status text not null default 'needs_review'
    check (review_status in ('published','needs_review','rejected')),
  confidence numeric(4,3),
  evidence jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  raw_activity jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Runtime configuration. Secrets should stay in environment variables.
create table if not exists public.config_managements (
  id bigserial primary key,
  config_key text not null unique,
  config_value text not null default '',
  description text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- System/admin-maintained WeChat official account QR login sessions.
create table if not exists public.wechat_auth_sessions (
  id uuid primary key default gen_random_uuid(),
  maintained_by uuid references auth.users(id) on delete set null,
  status text not null check (status in ('waiting','scanned','success','expired','error')),
  qr_path text,
  qr_signed_url text,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- WeChat login secrets. This table is service-role only.
create table if not exists public.wechat_auth_session_secret (
  session_id uuid primary key references public.wechat_auth_sessions(id) on delete cascade,
  token text,
  cookies_str text,
  expiry timestamptz,
  created_at timestamptz not null default now()
);

create or replace function public.claim_next_activity_extraction_run(
  p_worker_id text,
  p_stale_before timestamptz
)
returns setof public.activity_extraction_runs
language plpgsql
as $$
begin
  with stale_runs as (
    update public.activity_extraction_runs
    set
      status = 'failed',
      error = '活动抽取任务超时未完成，已标记为失败',
      finished_at = now(),
      locked_at = null,
      locked_by = null,
      updated_at = now()
    where status = 'processing'
      and coalesce(locked_at, started_at, created_at) < p_stale_before
    returning article_id, error
  )
  update public.articles
  set
    activity_extraction_status = 'failed',
    activity_extraction_error = stale_runs.error,
    updated_at = now()
  from stale_runs
  where public.articles.id = stale_runs.article_id;

  return query
  with next_run as (
    select id
    from public.activity_extraction_runs
    where status = 'queued'
      and attempt_count < max_attempts
    order by queued_at asc nulls last, created_at asc
    for update skip locked
    limit 1
  )
  update public.activity_extraction_runs as run
  set
    status = 'processing',
    locked_at = now(),
    locked_by = p_worker_id,
    started_at = now(),
    attempt_count = run.attempt_count + 1,
    error = '',
    updated_at = now()
  from next_run
  where run.id = next_run.id
  returning run.*;
end;
$$;

create or replace function public.claim_next_article_collection_item(
  p_worker_id text,
  p_stale_before timestamptz
)
returns setof public.article_collection_items
language plpgsql
as $$
begin
  update public.article_collection_items
  set
    status = 'failed',
    error = '文章采集任务超时未完成，已标记为失败',
    finished_at = now(),
    locked_at = null,
    locked_by = null,
    updated_at = now()
  where status = 'processing'
    and coalesce(locked_at, started_at, created_at) < p_stale_before;

  return query
  with next_item as (
    select id, run_id
    from public.article_collection_items
    where status = 'queued'
      and attempt_count < max_attempts
    order by queued_at asc nulls last, created_at asc
    for update skip locked
    limit 1
  ),
  mark_run as (
    update public.article_collection_runs as run
    set
      status = 'processing',
      started_at = coalesce(run.started_at, now()),
      updated_at = now()
    from next_item
    where run.id = next_item.run_id
      and run.status in ('queued','processing')
    returning run.id
  )
  update public.article_collection_items as item
  set
    status = 'processing',
    locked_at = now(),
    locked_by = p_worker_id,
    started_at = now(),
    attempt_count = item.attempt_count + 1,
    error = '',
    updated_at = now()
  from next_item
  where item.id = next_item.id
  returning item.*;
end;
$$;

create or replace function public.enqueue_pending_activity_extractions(
  p_prompt_version text
)
returns table (
  matched_count bigint,
  queued_count bigint,
  skipped_count bigint
)
language plpgsql
as $$
declare
  v_matched_count bigint := 0;
  v_queued_count bigint := 0;
begin
  select count(*)
  into v_matched_count
  from public.articles
  where activity_extraction_status = 'pending';

  with candidates as (
    select article.id
    from public.articles as article
    where article.activity_extraction_status = 'pending'
      and not exists (
        select 1
        from public.activity_extraction_runs as active_run
        where active_run.article_id = article.id
          and active_run.status in ('queued', 'processing')
      )
    order by article.created_at, article.id
    for update of article skip locked
  ),
  inserted as (
    insert into public.activity_extraction_runs (
      article_id,
      status,
      model,
      prompt_version,
      input_snapshot,
      queued_at
    )
    select
      candidates.id,
      'queued',
      '',
      p_prompt_version,
      '{}'::jsonb,
      now()
    from candidates
    on conflict do nothing
    returning article_id
  ),
  updated as (
    update public.articles as article
    set
      activity_extraction_status = 'processing',
      activity_extraction_error = '',
      updated_at = now()
    from inserted
    where article.id = inserted.article_id
    returning article.id
  )
  select count(*)
  into v_queued_count
  from updated;

  return query
  select
    v_matched_count,
    v_queued_count,
    greatest(v_matched_count - v_queued_count, 0);
end;
$$;

create or replace function public.claim_next_article_collection_run(
  p_worker_id text,
  p_stale_before timestamptz
)
returns setof public.article_collection_runs
language plpgsql
as $$
declare
  got_lock boolean;
begin
  got_lock := pg_try_advisory_xact_lock(hashtext('article_collection_runs_serial'));
  if not got_lock then
    return;
  end if;

  update public.article_collection_items
  set
    status = 'failed',
    error = '文章采集任务超时未完成，已标记为失败',
    finished_at = now(),
    locked_at = null,
    locked_by = null,
    updated_at = now()
  where status = 'processing'
    and coalesce(locked_at, started_at, created_at) < p_stale_before;

  update public.article_collection_runs
  set
    status = 'failed',
    error = '文章采集任务超时未完成，已标记为失败',
    finished_at = now(),
    updated_at = now()
  where status = 'processing'
    and coalesce(started_at, created_at) < p_stale_before
    and not exists (
      select 1
      from public.article_collection_items
      where run_id = public.article_collection_runs.id
        and status = 'processing'
    );

  return query
  with next_run as (
    select run.id
    from public.article_collection_runs as run
    where run.status = 'queued'
      and exists (
        select 1
        from public.article_collection_items as item
        where item.run_id = run.id
          and item.status = 'queued'
          and item.attempt_count < item.max_attempts
      )
      and not exists (
        select 1
        from public.article_collection_runs
        where status = 'processing'
      )
    order by run.created_at asc
    for update skip locked
    limit 1
  )
  update public.article_collection_runs as run
  set
    status = 'processing',
    started_at = coalesce(run.started_at, now()),
    updated_at = now()
  from next_run
  where run.id = next_run.id
  returning run.*;
end;
$$;

-- Indexes.
create index if not exists idx_profiles_role on public.profiles(role);
create index if not exists idx_profiles_status on public.profiles(status);
create index if not exists idx_articles_wechat_account_id_publish_time on public.articles(wechat_account_id, publish_time desc);
create index if not exists idx_articles_publish_time on public.articles(publish_time desc);
create index if not exists idx_articles_content_fetch_status on public.articles(content_fetch_status);
create index if not exists idx_articles_activity_extraction_status on public.articles(activity_extraction_status);
create index if not exists idx_wechat_accounts_status on public.wechat_accounts(status);
create index if not exists idx_wechat_accounts_group_id on public.wechat_accounts(group_id);
create index if not exists idx_article_collection_runs_status_created on public.article_collection_runs(status, created_at desc);
create index if not exists idx_article_collection_items_run_created on public.article_collection_items(run_id, created_at asc);
create index if not exists idx_article_collection_items_queue
  on public.article_collection_items(status, queued_at asc, created_at asc)
  where status = 'queued';
create unique index if not exists idx_article_collection_items_one_active_account
  on public.article_collection_items(wechat_account_id)
  where status in ('queued','processing');
create index if not exists idx_activity_extraction_runs_article_created on public.activity_extraction_runs(article_id, created_at desc);
create index if not exists idx_activity_extraction_runs_status_created on public.activity_extraction_runs(status, created_at desc);
create index if not exists idx_activity_extraction_runs_queue
  on public.activity_extraction_runs(status, queued_at asc, created_at asc)
  where status = 'queued';
create unique index if not exists idx_activity_extraction_runs_one_active_article
  on public.activity_extraction_runs(article_id)
  where status in ('queued','processing');
create index if not exists idx_activities_article_id on public.activities(article_id);
create index if not exists idx_activities_source_wechat_account_start_at on public.activities(source_wechat_account_id, start_at desc);
create index if not exists idx_activities_review_status_start_at on public.activities(review_status, start_at desc);
create index if not exists idx_activities_event_status_start_at on public.activities(event_status, start_at desc);
create index if not exists idx_activities_created_at on public.activities(created_at desc);
create index if not exists idx_config_managements_key on public.config_managements(config_key);
create index if not exists idx_config_managements_updated_at on public.config_managements(updated_at desc);
create index if not exists idx_wechat_auth_sessions_maintained_by on public.wechat_auth_sessions(maintained_by);
create index if not exists idx_wechat_auth_sessions_status on public.wechat_auth_sessions(status);
create index if not exists idx_wechat_auth_sessions_updated on public.wechat_auth_sessions(updated_at);
create index if not exists idx_article_images_article_id on public.article_images(article_id);
create index if not exists idx_article_images_object_path on public.article_images(object_path);
create index if not exists idx_article_images_article_position on public.article_images(article_id, position);
create index if not exists idx_article_images_ocr_status on public.article_images(ocr_status);

-- updated_at triggers.
drop trigger if exists trg_profiles_updated on public.profiles;
create trigger trg_profiles_updated before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists trg_wechat_account_groups_updated on public.wechat_account_groups;
create trigger trg_wechat_account_groups_updated before update on public.wechat_account_groups
for each row execute function public.set_updated_at();

drop trigger if exists trg_wechat_accounts_updated on public.wechat_accounts;
create trigger trg_wechat_accounts_updated before update on public.wechat_accounts
for each row execute function public.set_updated_at();

drop trigger if exists trg_articles_updated on public.articles;
create trigger trg_articles_updated before update on public.articles
for each row execute function public.set_updated_at();

drop trigger if exists trg_article_collection_runs_updated on public.article_collection_runs;
create trigger trg_article_collection_runs_updated before update on public.article_collection_runs
for each row execute function public.set_updated_at();

drop trigger if exists trg_article_collection_items_updated on public.article_collection_items;
create trigger trg_article_collection_items_updated before update on public.article_collection_items
for each row execute function public.set_updated_at();

drop trigger if exists trg_activities_updated on public.activities;
create trigger trg_activities_updated before update on public.activities
for each row execute function public.set_updated_at();

drop trigger if exists trg_activity_extraction_runs_updated on public.activity_extraction_runs;
create trigger trg_activity_extraction_runs_updated before update on public.activity_extraction_runs
for each row execute function public.set_updated_at();

drop trigger if exists trg_config_managements_updated on public.config_managements;
create trigger trg_config_managements_updated before update on public.config_managements
for each row execute function public.set_updated_at();

drop trigger if exists trg_wechat_auth_sessions_updated on public.wechat_auth_sessions;
create trigger trg_wechat_auth_sessions_updated before update on public.wechat_auth_sessions
for each row execute function public.set_updated_at();
