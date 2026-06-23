# 公众号分组定时采集设计

## 背景

系统当前支持在公众号分组页面手动发起文章采集。后端通过 `enqueue_group_collection()` 创建 `article_collection_runs` 和 `article_collection_items`，再由 FastAPI 内的单 worker 消费队列。

本功能在现有链路前增加轻量定时触发能力。调度器只负责按计划调用已有分组入队服务，不实现新的采集逻辑，也不改变 worker 的并发、重试、冷却或 stale 任务处理规则。

当前部署只运行一个 FastAPI 后端实例。本设计以单实例调度为边界，不增加分布式调度器或多实例抢占协议。

## 目标

- 允许管理员以公众号分组为单位配置每日定时采集。
- 每个分组最多存在一个启用中的采集计划。
- 计划触发后复用现有分组采集队列和 worker。
- 调度配置在服务重启后保留。
- 服务停机错过计划时间时不补偿，下一天继续执行。
- 在公众号分组页面完成配置、启停和最近结果查看。

## 非目标

- 不支持完整 Cron 表达式。
- 不支持固定间隔或每周计划。
- 不支持一个分组配置多个计划。
- 不支持错过任务补偿或多日追赶。
- 不支持调度失败当天自动重试。
- 不新增独立的调度任务管理页面或调度历史页面。
- 不设计多 FastAPI 实例下的分布式调度。
- 不把 OCR 纳入定时流程。

## 用户体验

### 分组列表

公众号分组列表增加“定时采集”列：

- 未配置或停用时显示“未启用”。
- 启用时显示“每天 HH:mm · N 页”。
- 同一区域展示最近一次定时触发时间和结果。
- 最近结果区分触发失败、排队中、采集中、成功、部分成功和失败。

不展示“下次执行时间”。每日执行时间已足够表达计划，而停机错过不补偿，因此额外计算下次执行时间没有必要。

### 操作

分组操作区保留现有“采集”，新增“定时设置”。

“定时设置”弹窗包含：

- 启用开关；
- 每日执行时间；
- 采集页数，范围 `1–5`，默认 `1`；
- 保存和取消操作。

定时采集始终从起始页 `0` 开始。手动“采集”继续使用现有流程，并且不会修改定时计划的当天触发标记。

## 数据模型

直接在 `wechat_account_groups` 增加调度字段：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `schedule_enabled` | boolean | `false` | 是否启用每日定时采集 |
| `schedule_time` | time | `null` | 每日执行时间 |
| `collection_pages` | integer | `1` | 从第 0 页开始采集的页数，限制为 1–5 |
| `last_scheduled_date` | date | `null` | 最近一次已尝试触发的本地日期，用于当天去重 |
| `last_scheduled_at` | timestamptz | `null` | 最近一次触发尝试时间 |
| `last_collection_run_id` | uuid | `null` | 最近一次成功创建的采集 run |
| `last_schedule_error` | text | `''` | 最近一次调度入队错误 |

`last_collection_run_id` 引用 `article_collection_runs(id)`，删除 run 时使用 `on delete set null`。删除分组时，调度字段随分组删除；已经创建的采集 run 延续当前 `group_id on delete set null` 行为，不取消已经入队的 item。

由于 initial schema 先创建 `wechat_account_groups`、后创建 `article_collection_runs`，`last_collection_run_id` 列先以普通 `uuid` 创建，并在 `article_collection_runs` 创建完成后通过 `alter table` 添加外键，避免初始化时引用尚不存在的表。

数据库必须约束：

- `collection_pages between 1 and 5`；
- `schedule_enabled = true` 时 `schedule_time` 不得为空。

数据库变更需要同时完成：

1. 新增一份增量 migration，供已有环境升级；
2. 同步更新 `supabase/migrations/20241120_initial_schema.sql`，供全新环境初始化。

## API 设计

新增独立接口更新调度配置：

```text
PUT /api/v1/wx/wechat-account-groups/{group_id}/schedule
```

请求示例：

```json
{
  "enabled": true,
  "time": "00:30",
  "collection_pages": 1
}
```

规则：

- 仅管理员可调用。
- 启用时必须提供合法时间。
- `collection_pages` 必须为 `1–5` 的整数。
- 停用计划只更新配置，不取消已经入队的采集任务。
- 普通分组创建和编辑接口不接受调度字段，避免权限和业务边界混杂。

分组列表响应增加调度配置字段，并批量补充 `last_collection_run_id` 对应的 run 摘要。后端一次查询相关 run，避免前端逐行请求。

## 调度器设计

FastAPI 生命周期启动一个进程内调度循环，并在应用关闭时停止。

调度循环每 30 秒执行一次：

1. 使用 `Asia/Shanghai` 计算当前本地日期和 `HH:MM`。
2. 查询 `schedule_enabled = true` 且分组 `status` 为启用状态的分组。
3. 只处理 `schedule_time` 与当前 `HH:MM` 相同的分组。
4. `last_scheduled_date` 已是当天时跳过。
5. 在调用入队服务前记录 `last_scheduled_date` 和 `last_scheduled_at`，保证同一分钟内不会因失败而重复触发。
6. 调用现有 `enqueue_group_collection(group_id, start_page=0, max_page=collection_pages)`。
7. 成功时保存 `last_collection_run_id` 并清空 `last_schedule_error`。
8. 失败时保存简短错误到 `last_schedule_error` 并写服务日志，当天不再重试。

服务启动时不会扫描历史日期，也不会补偿已经错过的执行时间。只有当前时间进入计划对应的分钟窗口时才会触发。

调度器不直接执行采集。公众号停用检查、已有运行任务去重、采集冷却、item 创建、worker 重试和 stale 恢复仍由现有采集服务负责。

## 一致性与失败处理

当前为单 FastAPI 实例，因此进程内调度循环不会与另一个调度实例竞争。持久化的 `last_scheduled_date` 提供服务内重入和同日去重。

设计采用“当天至多尝试一次”语义：

- 标记触发日期成功、随后入队失败时，当天不会重试；页面和日志记录触发失败。
- 入队成功后由现有 collection run/item 状态表示执行结果。
- 服务在计划分钟停机时不会产生触发记录，也不会在恢复后补跑。
- 手动采集和定时采集共享运行中去重与冷却规则，但手动采集不改变 `last_scheduled_date`。

如果未来部署扩展到多个 FastAPI 实例，需要重新设计数据库原子抢占或使用外部调度器；不应直接复用本设计的单实例假设。

## 权限

- 查看分组时可读取调度展示字段。
- 创建、修改、启用或停用调度计划必须使用与现有分组管理一致的管理员授权。
- 调度循环使用后端服务权限访问 Supabase，不依赖用户会话。

## 测试策略

### 后端

- 当前时间命中计划时调用分组入队服务。
- 当前时间未命中时不触发。
- 调度计划停用时不触发。
- 分组停用时不触发。
- 同一分组同一天最多尝试一次。
- 服务启动不会补偿错过的任务。
- 入队异常会记录错误且当天不再重试。
- 成功入队会保存 run ID 并清空旧错误。
- 手动采集不会修改定时触发标记。
- 调度配置接口执行管理员授权和参数校验。
- 分组列表批量返回最近 run 摘要。

### 数据库

- 增量 migration 可应用到现有 schema。
- `20241120_initial_schema.sql` 包含相同字段、默认值、外键和约束。
- 非法 `collection_pages` 被数据库拒绝。
- 启用计划但未设置 `schedule_time` 被数据库拒绝。

### 前端

- 未启用和已启用计划展示正确。
- 设置弹窗能够加载、校验和保存时间及页数。
- 最近调度错误和 collection run 状态展示正确。
- 手动采集入口保持原有行为。

## 验收标准

- 管理员可以在公众号分组页面启用、编辑和停用每日定时采集。
- 每个分组最多只有一个每日计划。
- 定时触发始终从第 0 页开始，并按配置采集 1–5 页。
- 到点后通过现有分组入队服务创建采集任务。
- 同一分组同一天不会重复定时触发。
- 服务停机错过任务后不会补偿，下一天按计划继续。
- 页面可以查看计划配置和最近一次结果。
- 增量 migration 与 initial schema 保持一致。
