# Review Findings Optimization Design

## Goal

修复代码审查中已确认的权限、敏感信息暴露、认证重试、异步阻塞、前端首屏体积和校验脚本兼容性问题，同时明确不修改以下内容：

- Supabase service-role 客户端的 `verify=False` 配置。
- 默认管理员账号和密码。
- `data/wx.lic` 的现有 session 存储格式。

## Backend authorization and response boundaries

微信公众号扫码授权和系统运行信息属于管理员能力。所有 `/auth/qr/*` 接口，以及 `/sys/info`、`/sys/resources`，统一依赖 `get_current_admin_user`。普通登录用户访问时返回 HTTP 403。

`/sys/info` 只返回前端展示所需的公众号授权状态、过期时间和可用性，不返回运行时 session、cookies、token 或其他可复用凭据。现有系统页展示字段保持兼容。

## Authentication retries

Supabase Auth 用户校验保留最多三次尝试，但只重试网络异常、HTTP 429 和 HTTP 5xx。401、403 以及其他确定性 4xx 响应立即返回认证失败，不执行退避等待。

每次请求使用的 HTTP 客户端生命周期保持局部，避免在本次改动中引入全局连接管理重构。

## Async database execution

保留当前同步 Supabase Python SDK 和仓储公开异步接口。所有可能阻塞的 `.execute()` 调用通过 `asyncio.to_thread` 调度到工作线程，避免占用 FastAPI 事件循环。

修改集中在通用 `SupabaseClient` 封装以及认证模块中直接调用同步 SDK 的位置。业务仓储接口和返回值结构保持不变。

## Frontend route splitting

顶层布局和登录页保持同步加载，其余业务页面改为 `React.lazy` 动态导入。路由内容使用统一 `Suspense` fallback，继续使用现有 Ant Design 加载样式，不引入新的 UI 组件或依赖。

构建结果应产生多个页面 chunk，主入口体积应显著低于当前约 1.47 MB 的单文件结果。

## Validation script

`validate.sh` 按以下顺序选择 Python：

1. `backend/.venv/bin/python`
2. `python3`
3. `python`

如果均不存在，输出明确错误。其他校验行为不变。

## Testing

后端采用测试先行：

- 普通用户不能访问二维码和系统管理接口。
- `/sys/info` 响应不包含 session。
- 确定性 4xx 不重试，429、5xx 和网络异常仍重试。
- Supabase 同步执行通过线程调度，返回值保持一致。

前端通过现有 TypeScript 构建和 Node 测试验证，额外检查 Vite 输出存在多个路由 chunk。校验脚本必须在当前仅提供 `python3` 或项目虚拟环境的环境中通过。

最终执行完整后端 unittest、前端测试、前端生产构建、Python compileall 和 `validate.sh`。
