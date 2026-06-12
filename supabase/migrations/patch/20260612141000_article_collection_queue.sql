-- Add a queued worker model for WeChat article collection.

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

alter table public.article_collection_runs enable row level security;
alter table public.article_collection_items enable row level security;

revoke all on public.article_collection_runs from anon;
revoke all on public.article_collection_runs from authenticated;
revoke all on public.article_collection_items from anon;
revoke all on public.article_collection_items from authenticated;
grant all on public.article_collection_runs to service_role;
grant all on public.article_collection_items to service_role;
grant usage, select on all sequences in schema public to service_role;

drop policy if exists "article_collection_runs_service_role_all" on public.article_collection_runs;
create policy "article_collection_runs_service_role_all"
on public.article_collection_runs for all
to service_role
using (true)
with check (true);

drop policy if exists "article_collection_items_service_role_all" on public.article_collection_items;
create policy "article_collection_items_service_role_all"
on public.article_collection_items for all
to service_role
using (true)
with check (true);

revoke all on function public.claim_next_article_collection_item(text, timestamptz) from public;
grant execute on function public.claim_next_article_collection_item(text, timestamptz) to service_role;

create index if not exists idx_article_collection_runs_status_created
  on public.article_collection_runs(status, created_at desc);

create index if not exists idx_article_collection_items_run_created
  on public.article_collection_items(run_id, created_at asc);

create index if not exists idx_article_collection_items_queue
  on public.article_collection_items(status, queued_at asc, created_at asc)
  where status = 'queued';

create unique index if not exists idx_article_collection_items_one_active_account
  on public.article_collection_items(wechat_account_id)
  where status in ('queued','processing');

drop trigger if exists trg_article_collection_runs_updated on public.article_collection_runs;
create trigger trg_article_collection_runs_updated before update on public.article_collection_runs
for each row execute function public.set_updated_at();

drop trigger if exists trg_article_collection_items_updated on public.article_collection_items;
create trigger trg_article_collection_items_updated before update on public.article_collection_items
for each row execute function public.set_updated_at();

notify pgrst, 'reload schema';
