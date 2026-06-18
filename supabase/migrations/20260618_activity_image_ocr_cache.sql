alter table public.article_images
  add column if not exists ocr_status text not null default 'pending',
  add column if not exists ocr_text text not null default '',
  add column if not exists ocr_confidence double precision,
  add column if not exists ocr_provider text not null default '',
  add column if not exists ocr_error text not null default '',
  add column if not exists ocr_finished_at timestamptz;

alter table public.article_images
  drop constraint if exists article_images_ocr_status_check;

alter table public.article_images
  add constraint article_images_ocr_status_check
  check (ocr_status in ('pending', 'completed', 'failed'));

create index if not exists idx_article_images_ocr_status
  on public.article_images(ocr_status);
