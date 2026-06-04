-- RLS and grants for the FastAPI-only frontend architecture.
--
-- Frontend business data access goes through FastAPI. Supabase tables are the
-- backend data layer, so anon/authenticated roles do not get broad table access.

alter table public.profiles enable row level security;
alter table public.wechat_accounts enable row level security;
alter table public.articles enable row level security;
alter table public.article_images enable row level security;
alter table public.activities enable row level security;
alter table public.wechat_account_groups enable row level security;
alter table public.config_managements enable row level security;
alter table public.wechat_auth_sessions enable row level security;
alter table public.wechat_auth_session_secret enable row level security;

-- Data API grants are explicit. Do not grant broad table access to anon or
-- authenticated; FastAPI uses the service role and enforces business auth.
grant usage on schema public to anon, authenticated;

revoke all on all tables in schema public from anon;
revoke all on all tables in schema public from authenticated;
revoke all on all sequences in schema public from anon;
revoke all on all sequences in schema public from authenticated;

grant usage on schema public to service_role;
grant all on all tables in schema public to service_role;
grant all on all sequences in schema public to service_role;

-- profiles: user-owned policies kept for defense in depth if direct
-- authenticated access is ever needed. Business APIs still go through FastAPI.
drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
on public.profiles for select
to authenticated
using (auth.uid() is not null and auth.uid() = user_id);

drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own"
on public.profiles for insert
to authenticated
with check (auth.uid() is not null and auth.uid() = user_id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
on public.profiles for update
to authenticated
using (auth.uid() is not null and auth.uid() = user_id)
with check (auth.uid() is not null and auth.uid() = user_id);

-- Backend-managed shared data. These policies are intentionally service role
-- only because normal product access is mediated by FastAPI.
drop policy if exists "wechat_accounts_service_role_all" on public.wechat_accounts;
create policy "wechat_accounts_service_role_all"
on public.wechat_accounts for all
to service_role
using (true)
with check (true);

drop policy if exists "articles_service_role_all" on public.articles;
create policy "articles_service_role_all"
on public.articles for all
to service_role
using (true)
with check (true);

drop policy if exists "article_images_service_role_all" on public.article_images;
create policy "article_images_service_role_all"
on public.article_images for all
to service_role
using (true)
with check (true);

drop policy if exists "activities_service_role_all" on public.activities;
create policy "activities_service_role_all"
on public.activities for all
to service_role
using (true)
with check (true);

drop policy if exists "wechat_account_groups_service_role_all" on public.wechat_account_groups;
create policy "wechat_account_groups_service_role_all"
on public.wechat_account_groups for all
to service_role
using (true)
with check (true);

drop policy if exists "config_managements_service_role_all" on public.config_managements;
create policy "config_managements_service_role_all"
on public.config_managements for all
to service_role
using (true)
with check (true);

drop policy if exists "wechat_auth_sessions_service_role_all" on public.wechat_auth_sessions;
create policy "wechat_auth_sessions_service_role_all"
on public.wechat_auth_sessions for all
to service_role
using (true)
with check (true);

drop policy if exists "wechat_auth_session_secret_service_role_all" on public.wechat_auth_session_secret;
create policy "wechat_auth_session_secret_service_role_all"
on public.wechat_auth_session_secret for all
to service_role
using (true)
with check (true);
