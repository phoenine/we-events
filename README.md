# we-events

we-events 用于集中采集微信公众号文章，抽取其中的活动信息，并向登录用户展示统一整理后的文章与活动数据。

当前产品方向是不再按每个普通用户分别维护公众号登录态，而是由系统/admin 维护一个微信公众号采集身份，统一采集数据后通过 FastAPI 提供给前端。

## 核心能力

- Supabase Auth 用户登录与业务 profile 管理
- admin 维护微信公众号扫码授权状态
- 公众号信息维护、分组、文章采集与文章图片入库
- 文章列表、清理、批量删除与采集触发
- 活动信息管理与后续 LLM 兜底抽取预留
- React + Vite + Ant Design 前端
- FastAPI + Supabase + Playwright 后端

## 架构约定

- 前端只访问 FastAPI，不直接访问 Supabase。
- 后端使用 Supabase service role 访问业务表。
- 公众号二维码授权入口只面向 admin，当前放在前端系统页 `/sys`。
- 公众号采集身份是系统级凭据，不绑定普通登录用户。
- 当前阶段不保留 PDF、webhook/notice、cron UI 等旧产品功能。

## 目录结构

```text
.
├── backend/                 # FastAPI 后端
├── frontend/                # React + Vite 前端
├── supabase/                # Supabase self-hosted compose、baseline schema、RLS、seed 文档
├── docker-compose.yaml      # 本地容器编排
├── validate.sh              # Backend + Supabase 结构校验
└── .github/workflows/       # Docker image build workflow
```

## 本地开发

### 1. 配置 Supabase

本项目支持两类 Supabase 环境：

- 本地 self-hosted Supabase：通常由另一套 Docker Compose 暴露 API/Kong 到宿主机端口 `8000`。
- Supabase online：使用 Supabase Dashboard 中的 project URL 和 API keys。

Docker Compose 使用根目录 env 文件选择 Supabase 环境，不要提交真实 `.env.local` / `.env.online`：

```bash
cp .env.local.example .env.local
# 或者
cp .env.online.example .env.online

# 直接调试后端时再复制这个文件
cp backend/.env.example backend/.env
```

本地 self-hosted Supabase 编排与环境变量隔离在 `supabase/` 目录。先把旧项目的 `volumes/` 目录迁到 `supabase/volumes/`，再启动 Supabase：

```bash
cd supabase
docker compose up -d
```

本地 self-hosted 后端容器默认通过 `http://host.docker.internal:8000` 访问宿主机 Supabase API。确保 Supabase API、Postgres、Storage 等容器已启动，并按 `supabase/README.md` 初始化 schema、RLS、seed 和 Storage bucket。

默认后端会读取：

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_KEY`

Docker Compose 运行时推荐放在根目录 `.env.local` 或 `.env.online`。直接在 `backend/` 里运行 Python/debug 时，后端会读取 `backend/.env`。

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
python init_sys.py
python main.py
```

默认 API 前缀：

```text
/api/v1/wx
```

接口文档：

```text
http://localhost:38001/api/docs
```

### 3. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

开发环境通过 Vite proxy 转发 `/api` 到后端，配置见 `frontend/vite.config.ts`。

## Docker

根目录提供 `docker-compose.yaml`：

```bash
docker compose --env-file .env.local up --build

# 或者使用线上 Supabase
docker compose --env-file .env.online up --build
```

默认端口：

- Backend: `http://localhost:38001`
- Frontend: `http://localhost:30000`

Compose 通过根目录 `.env.local` / `.env.online` 选择 Supabase 环境。`backend/.env` 只用于直接运行后端做 debug，Docker Compose 不读取它。如果宿主机 Supabase 运行在 Docker/OrbStack 中，后端容器默认通过 `host.docker.internal` 访问 Supabase API。

## GitHub Actions

`.github/workflows/build-and-deploy.yml` 会在 `main`、`dev` 分支 push 以及 PR 时构建 backend/frontend Docker image。

- push：构建并推送到 GHCR。
- pull request：只构建校验，不推送镜像。

Docker tag 使用 branch/pr/sha 规则，sha tag 格式为 `sha-xxxxxxx`。

## 校验

后端与 Supabase 结构校验：

```bash
bash validate.sh
```

前端构建：

```bash
cd frontend
pnpm build
```

后端语法检查：

```bash
python -m compileall -q backend
```

## 当前注意事项

- LLM 兜底抽取目前只保留在需求方向中，暂未做完整设计。
- 公众号扫码登录可能超时，失败后需要重新申请二维码。
- `admin@example.com` 的管理员身份来自 `public.profiles.role = admin`，不是单纯按邮箱判断。
