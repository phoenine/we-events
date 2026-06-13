# we-events Frontend

前端已从旧 Vue 版本迁移为 React + Vite + TypeScript，主组件库使用 Ant Design。前端只通过 FastAPI 访问业务接口，不直接连接 Supabase。

## 技术栈

- React 18
- Vite
- TypeScript
- Ant Design
- React Router
- TanStack Query
- Zustand
- Axios
- DOMPurify

## 功能范围

- 用户登录、退出、资料与密码修改
- 文章列表、公众号筛选、采集触发、批量删除、清理无效/重复/过期文章
- 公众号列表、添加公众号、关键词搜索公众号、通过文章链接回填公众号信息
- 公众号分组管理
- 活动列表与活动状态展示
- 系统配置与系统信息
- admin-only 系统页，维护微信公众号二维码授权

## 目录结构

```text
frontend/
├── src/
│   ├── api/                 # FastAPI 客户端封装
│   ├── app/                 # App 根组件与路由
│   ├── components/          # 通用组件与布局
│   ├── pages/               # 页面
│   ├── store/               # Zustand 状态
│   ├── types/               # API 类型
│   ├── utils/               # auth/time 等工具
│   ├── main.tsx             # React 入口
│   └── styles.css           # 全局样式
├── Dockerfile
├── nginx.conf
├── package.json
└── vite.config.ts
```

## 环境变量

开发环境可创建 `frontend/.env.development`：

```ini
DEV_PROXY_TARGET=http://localhost:38001
```

说明：

- 前端 API baseURL 固定为 `/api/v1`。
- 开发时 Vite proxy 将 `/api` 转发到 `DEV_PROXY_TARGET`。
- 生产 Docker 镜像中由 nginx 将 `/api/` 代理到 `backend:38001`。

## 本地运行

安装依赖：

```bash
pnpm install
```

启动开发服务器：

```bash
pnpm dev
```

生产构建：

```bash
pnpm build
```

## Docker

构建镜像：

```bash
docker build -f Dockerfile . -t wx-activity-frontend
```

或者在项目根目录通过 compose 启动：

```bash
docker compose up --build frontend
```

默认前端端口：

```text
http://localhost:30000
```

## 权限说明

- 系统页 `/sys` 仅 `role=admin` 可访问。
- 侧边栏“系统”菜单也只在当前用户为 admin 时显示。
- admin 身份来自后端 `/user` 返回的 `role`，对应 Supabase `public.profiles.role`。

## 迁移说明

旧 Vue 代码已移除。当前迁移说明与剩余补齐项见：

```text
frontend/REACT_MIGRATION_SPEC.md
```
