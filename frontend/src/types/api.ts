export interface ApiList<T> {
  list: T[];
  total: number;
}

export interface WechatAccount {
  id: string;
  name: string;
  mp_name?: string;
  logo_url?: string;
  mp_cover?: string;
  description?: string;
  mp_intro?: string;
  faker_id?: string;
  status?: number;
  last_fetch?: string;
  last_publish?: string;
  update_time?: string;
  sync_time?: string;
  article_count?: number;
}

export interface WechatAccountGroup {
  id: string;
  name: string;
  description?: string;
  status?: number;
  wechat_account_ids?: string[] | string;
  wechat_account_count?: number;
  schedule_enabled?: boolean;
  schedule_time?: string | null;
  collection_pages?: number;
  last_scheduled_date?: string | null;
  last_scheduled_at?: string | null;
  last_collection_run_id?: string | null;
  last_schedule_error?: string;
  last_collection_run?: ArticleCollectionRunSummary | null;
}

export interface ArticleCollectionRunSummary {
  id: string;
  status:
    | "queued"
    | "processing"
    | "success"
    | "partial_success"
    | "failed"
    | "canceled";
  articles_count?: number;
  error?: string;
  created_at?: string;
  finished_at?: string;
}

export interface WechatAccountGroupScheduleUpdate {
  enabled: boolean;
  time?: string | null;
  collection_pages: number;
}

export interface Article {
  id: string;
  title: string;
  description?: string;
  pic_url?: string;
  content?: string;
  content_md?: string;
  url?: string;
  link?: string;
  mp_name?: string;
  wechat_account_id?: string;
  publish_time?: string;
  publish_at?: string;
  created_at?: string;
  content_fetch_status?: string;
  activity_extraction_status?: string;
}

export interface ActivityExtractionSummary {
  pending_count: number;
  processing_count: number;
}

export interface ActivityExtractionBatchResult {
  matched_count: number;
  queued_count: number;
  skipped_count: number;
}

export interface ActivityCleanupResult {
  message: string;
  deleted_count: number;
}

export interface Activity {
  id: string;
  article_id: string;
  extraction_run_id?: string;
  source_wechat_account_id?: string;
  article_url?: string;
  title: string;
  summary?: string;
  event_time_text?: string;
  start_at?: string;
  end_at?: string;
  event_status?: "upcoming" | "ongoing" | "ended" | "unknown";
  location_text?: string;
  registration_text?: string;
  registration_method?: "qr_code" | "link" | "phone" | "wechat" | "onsite" | "none" | "unknown";
  registration_url?: string;
  qr_image_urls?: string[];
  fee_text?: string;
  audience?: string;
  review_status?: "published" | "needs_review" | "rejected";
  confidence?: number;
  evidence?: Array<Record<string, unknown>>;
  warnings?: string[];
  raw_activity?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface ActivityImageOcrResult {
  id: string;
  position?: number;
  text: string;
  provider?: string;
}

export interface ActivityImageEnrichmentContext {
  activity: Activity;
  missing_fields: string[];
  image_count: number;
  images: Array<{
    id: string;
    public_url?: string;
    origin_url?: string;
    position?: number;
    ocr_status?: "pending" | "completed" | "failed";
  }>;
  ocr_enabled: boolean;
}

export interface ActivityImageEnrichmentPreview {
  activity_id: string;
  current: Activity;
  suggestions: Partial<Activity>;
  evidence: Array<Record<string, unknown>>;
  warnings: string[];
  images: ActivityImageOcrResult[];
}

export interface ConfigItem {
  key: string;
  value: unknown;
  description?: string;
  created_at?: string;
  updated_at?: string;
}
