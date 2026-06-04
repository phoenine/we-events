# Supabase Baseline Setup

This directory defines the clean Supabase baseline for fresh environments.

The project uses Supabase as the backend data layer. The frontend does not query Supabase tables directly; all product data access goes through FastAPI.

## Execution Order

Apply SQL in this order:

1. `supabase/migrations/20241120_initial_schema.sql`
2. `supabase/migrations/20241120_rls_policies.sql`
3. `supabase/config_managements_seed.sql`

This is a clean baseline. Existing database data does not need migration for the current project plan.

## Required Storage Buckets

Create these Supabase Storage buckets:

- `qr`
  - Purpose: WeChat official account QR login images.
  - Access: private.
  - Backend returns signed URLs.
- `article-images`
  - Purpose: images downloaded from collected article HTML.
  - Access: public by current content rendering strategy.
  - Database mappings live in `article_images`.

## Architecture Decisions

### FastAPI-only frontend data access

The frontend should call FastAPI endpoints only. It should not use Supabase table clients directly.

Implications:

- Supabase Data API grants are intentionally narrow.
- `anon` and `authenticated` roles do not get broad business-table access.
- FastAPI uses the service role internally and enforces product permissions.

### Application users vs WeChat crawling identity

The project has two separate identities:

- Application users: log into the product through Supabase Auth.
- WeChat official-account crawling identity: maintained by admin/system through QR login.

Normal users do not maintain their own WeChat QR login sessions. The system/admin maintains one crawling identity, collects source data, and shares the resulting `wechat_accounts`, `articles`, and `activities` data through FastAPI.

### User profile model

Supabase Auth stores credentials and email. Business user state lives in `profiles`:

- `username`
- `nickname`
- `role`
- `status`

Do not use Supabase `user_metadata` as the business authorization source.

### Activity model

Product activities are stored in `activities`, not `events`.

`activities` are extracted from `articles` and are shared system data. They are not per-user crawl results.

### LLM fallback requirement

Default collection should use the system/admin-maintained WeChat crawling session.

LLM direct content reading is an expensive fallback path. It should be considered only when the WeChat login state is invalid or article content fetching fails.

This baseline records only the minimum schema boundary for that future fallback:

- `articles.content_fetch_status`
- `articles.activity_extraction_status`
- `activities.fallback_reason`
- `activities.extracted_by`
- `activities.extraction_model`
- `activities.extraction_raw`

Detailed LLM fallback workflow and cost audit design are intentionally deferred.

## Tables

Core tables:

- `profiles`
- `wechat_account_groups`
- `wechat_accounts`
- `articles`
- `article_images`
- `activities`
- `config_managements`
- `wechat_auth_sessions`
- `wechat_auth_session_secret`

## Permissions

RLS is enabled for all baseline tables.

The default posture is:

- FastAPI is the product authorization boundary.
- `service_role` can manage backend-owned tables.
- `anon` and `authenticated` do not receive broad access to shared business tables.
- `profiles` keeps user-owned policies for defense in depth.
- `wechat_auth_session_secret` is service-role only.

## Runtime Configuration Seed

`supabase/config_managements_seed.sql` can be run repeatedly. It upserts default runtime settings into `config_managements`.

Secrets must stay in environment variables or secure storage. Do not store these in `config_managements`:

- `SUPABASE_SERVICE_KEY`
- `LLM_API_KEY`
- WeChat cookies or tokens
