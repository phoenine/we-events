alter table public.wechat_account_groups
  add column if not exists schedule_enabled boolean not null default false,
  add column if not exists schedule_time time,
  add column if not exists collection_pages integer not null default 1,
  add column if not exists last_scheduled_date date,
  add column if not exists last_scheduled_at timestamptz,
  add column if not exists last_collection_run_id uuid,
  add column if not exists last_schedule_error text not null default '';

alter table public.wechat_account_groups
  drop constraint if exists wechat_account_groups_collection_pages_check,
  add constraint wechat_account_groups_collection_pages_check
    check (collection_pages between 1 and 5),
  drop constraint if exists wechat_account_groups_schedule_time_check,
  add constraint wechat_account_groups_schedule_time_check
    check (not schedule_enabled or schedule_time is not null);

alter table public.wechat_account_groups
  drop constraint if exists wechat_account_groups_last_collection_run_id_fkey,
  add constraint wechat_account_groups_last_collection_run_id_fkey
    foreign key (last_collection_run_id)
    references public.article_collection_runs(id)
    on delete set null;
