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

revoke all on function public.claim_next_article_collection_run(text, timestamptz) from public;
grant execute on function public.claim_next_article_collection_run(text, timestamptz) to service_role;
