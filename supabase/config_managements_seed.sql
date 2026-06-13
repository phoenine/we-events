-- 运行时配置初始化（可重复执行，按 config_key upsert）
insert into public.config_managements (config_key, config_value, description) values
  ('max_page', '5', '首次添加公众号时采集页数'),
  ('sync_interval', '60', '手动触发单个公众号更新的最小间隔（秒）'),
  ('interval', '10', '文章采集时每篇文章抓取间隔（秒）'),
  ('gather.model', 'app', '采集模式：app/web/api'),
  ('gather.content', 'true', '采集流程是否抓取正文内容')
on conflict (config_key) do update
set
  config_value = excluded.config_value,
  description = excluded.description,
  updated_at = now();
