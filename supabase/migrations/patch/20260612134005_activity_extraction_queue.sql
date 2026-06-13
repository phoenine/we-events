-- Upgrade existing environments to the queued activity extraction model.

alter table public.activity_extraction_runs
  add column if not exists queued_at timestamptz not null default now();

alter table public.activity_extraction_runs
  add column if not exists locked_at timestamptz;

alter table public.activity_extraction_runs
  add column if not exists locked_by text;

alter table public.activity_extraction_runs
  add column if not exists attempt_count integer not null default 0;

alter table public.activity_extraction_runs
  add column if not exists max_attempts integer not null default 1;

alter table public.activity_extraction_runs
  alter column status set default 'queued';

alter table public.activity_extraction_runs
  alter column started_at drop not null;

alter table public.activity_extraction_runs
  alter column started_at drop default;

alter table public.activity_extraction_runs
  drop constraint if exists activity_extraction_runs_status_check;

alter table public.activity_extraction_runs
  add constraint activity_extraction_runs_status_check
  check (status in ('queued','processing','success','not_activity','failed','fallback_required'));

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

revoke all on function public.claim_next_activity_extraction_run(text, timestamptz) from public;
grant execute on function public.claim_next_activity_extraction_run(text, timestamptz) to service_role;

create index if not exists idx_activity_extraction_runs_queue
  on public.activity_extraction_runs(status, queued_at asc, created_at asc)
  where status = 'queued';

drop index if exists public.idx_activity_extraction_runs_one_processing_article;

create unique index if not exists idx_activity_extraction_runs_one_active_article
  on public.activity_extraction_runs(article_id)
  where status in ('queued','processing');

notify pgrst, 'reload schema';
