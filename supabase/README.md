# Supabase Baseline Setup

This directory defines the clean Supabase baseline for fresh environments.

The project uses Supabase as the backend data layer. The frontend does not query Supabase tables directly; all product data access goes through FastAPI.

## Self-Hosted Docker

The self-hosted Supabase compose stack is kept in this directory so its env file, Docker volumes, and helper files do not pollute the application root.

Expected local layout:

```text
supabase/
├── .env                    # local Supabase compose environment, ignored by git
├── docker-compose.yml      # self-hosted Supabase stack
├── volumes/                # Kong, Postgres init, Storage files, and Studio snippets
├── migrations/
└── config_managements_seed.sql
```

This project does not use Supabase Edge Functions, Realtime, Supavisor/Pooler, Imgproxy, Analytics/Vector logging, or S3/MinIO-backed storage. Storage runs in local file mode for the `qr` and `article-images` buckets used by the backend.

The local prerequisite stack intentionally keeps only:

- Kong
- Auth
- PostgREST
- Storage
- Postgres
- Studio
- Postgres Meta

Start Supabase from this directory:

```bash
cd supabase
docker compose up -d
```

The application compose file remains at the project root as `docker-compose.yaml` and should be started separately.

## Execution Order

For a fresh Supabase environment, apply SQL in this order:

1. `supabase/migrations/20241120_initial_schema.sql`
2. `supabase/migrations/20241120_rls_policies.sql`
3. `supabase/config_managements_seed.sql`

For an existing online or local self-hosted environment created before the queue model, apply patch SQL after the baseline state as needed:

1. `supabase/migrations/patch/20260612134005_activity_extraction_queue.sql`
2. `supabase/migrations/patch/20260612141000_article_collection_queue.sql`
3. `supabase/migrations/patch/20260612143000_fix_article_collection_queue_grants.sql`

Fresh environments should prefer the clean baseline. Existing environments should apply patches in timestamp order.

## Environment Modes

The application supports both Supabase online and self-hosted local Supabase.

- Local self-hosted Docker Compose: use root `.env.local` with `SUPABASE_URL=http://host.docker.internal:8000` for backend containers.
- Online Docker Compose: use root `.env.online` with `SUPABASE_URL=https://<project-ref>.supabase.co`.
- Direct backend debug: use `backend/.env` and set the same Supabase URL/key values there.

Both environments must use the same schema, RLS policies, runtime seed, and required Storage buckets. Auth users and profile rows are environment-specific and are not shared between local and online.

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

Bucket names are configured through:

- `SUPABASE_QR_BUCKET=qr`
- `SUPABASE_ARTICLES_BUCKET=article-images`

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
