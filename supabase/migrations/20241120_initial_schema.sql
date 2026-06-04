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
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- WeChat official account subscription sources.
create table if not exists public.wechat_accounts (
  id text primary key,
  name text not null,
  description text,
  logo_url text,
  faker_id text unique,
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
    check (activity_extraction_status in ('pending','extracted','not_activity','failed','fallback_required')),
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
  created_at timestamptz not null default now(),
  unique (article_id, object_path)
);

-- Product activities extracted from articles.
create table if not exists public.activities (
  id uuid primary key default gen_random_uuid(),
  article_id text not null references public.articles(id) on delete cascade,
  source_wechat_account_id text references public.wechat_accounts(id) on delete set null,
  title text not null default '',
  original_title text not null default '',
  article_url text not null default '',
  registration_time_text text not null default '',
  registration_method text not null default '',
  event_time_text text not null default '',
  event_fee text not null default '',
  audience text not null default '',
  status text not null default 'active'
    check (status in ('active','archived','rejected')),
  extraction_status text not null default 'extracted'
    check (extraction_status in ('pending','extracted','reviewed','rejected','failed')),
  fallback_reason text,
  confidence numeric(4,3),
  extracted_by text not null default 'llm',
  extraction_model text,
  extraction_raw jsonb not null default '{}'::jsonb,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (article_id)
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

-- Indexes.
create index if not exists idx_profiles_role on public.profiles(role);
create index if not exists idx_profiles_status on public.profiles(status);
create index if not exists idx_articles_wechat_account_id_publish_time on public.articles(wechat_account_id, publish_time desc);
create index if not exists idx_articles_publish_time on public.articles(publish_time desc);
create index if not exists idx_articles_content_fetch_status on public.articles(content_fetch_status);
create index if not exists idx_articles_activity_extraction_status on public.articles(activity_extraction_status);
create index if not exists idx_wechat_accounts_status on public.wechat_accounts(status);
create index if not exists idx_wechat_accounts_group_id on public.wechat_accounts(group_id);
create index if not exists idx_activities_article_id on public.activities(article_id);
create index if not exists idx_activities_source_wechat_account_id on public.activities(source_wechat_account_id);
create index if not exists idx_activities_status on public.activities(status);
create index if not exists idx_activities_extraction_status on public.activities(extraction_status);
create index if not exists idx_activities_created_at on public.activities(created_at desc);
create index if not exists idx_config_managements_key on public.config_managements(config_key);
create index if not exists idx_config_managements_updated_at on public.config_managements(updated_at desc);
create index if not exists idx_wechat_auth_sessions_maintained_by on public.wechat_auth_sessions(maintained_by);
create index if not exists idx_wechat_auth_sessions_status on public.wechat_auth_sessions(status);
create index if not exists idx_wechat_auth_sessions_updated on public.wechat_auth_sessions(updated_at);
create index if not exists idx_article_images_article_id on public.article_images(article_id);
create index if not exists idx_article_images_object_path on public.article_images(object_path);

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

drop trigger if exists trg_activities_updated on public.activities;
create trigger trg_activities_updated before update on public.activities
for each row execute function public.set_updated_at();

drop trigger if exists trg_config_managements_updated on public.config_managements;
create trigger trg_config_managements_updated before update on public.config_managements
for each row execute function public.set_updated_at();

drop trigger if exists trg_wechat_auth_sessions_updated on public.wechat_auth_sessions;
create trigger trg_wechat_auth_sessions_updated before update on public.wechat_auth_sessions
for each row execute function public.set_updated_at();
