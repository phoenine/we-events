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

export interface ConfigItem {
  key: string;
  value: unknown;
  description?: string;
  created_at?: string;
  updated_at?: string;
}
