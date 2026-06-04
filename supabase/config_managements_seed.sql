-- 运行时配置初始化（可重复执行，按 config_key upsert）
insert into public.config_managements (config_key, config_value, description) values
  ('max_page', '5', '首次添加公众号时采集页数'),
  ('sync_interval', '60', '手动触发单个公众号更新的最小间隔（秒）'),
  ('interval', '10', '定时采集任务中每篇文章抓取间隔（秒）'),
  ('gather.model', 'app', '采集模式：app/web/api'),
  ('gather.content_mode', 'web', '文章补采模式：web/api'),
  ('gather.content_auto_check', 'false', '是否自动补采无内容文章'),
  ('gather.content_auto_interval', '59', '自动补采执行间隔（分钟）'),
  ('gather.content', 'true', '采集流程是否抓取正文内容')
on conflict (config_key) do update
set
  config_value = excluded.config_value,
  description = excluded.description,
  updated_at = now();
