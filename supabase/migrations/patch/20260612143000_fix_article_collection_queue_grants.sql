-- Ensure PostgREST service_role can consume article collection queue tables.
-- RLS policies do not grant table privileges; existing remote environments need
-- explicit grants after the queue tables are created.

revoke all on public.article_collection_runs from anon;
revoke all on public.article_collection_runs from authenticated;
revoke all on public.article_collection_items from anon;
revoke all on public.article_collection_items from authenticated;

grant all on public.article_collection_runs to service_role;
grant all on public.article_collection_items to service_role;
grant usage, select on all sequences in schema public to service_role;

revoke all on function public.claim_next_article_collection_item(text, timestamptz) from public;
grant execute on function public.claim_next_article_collection_item(text, timestamptz) to service_role;

notify pgrst, 'reload schema';
