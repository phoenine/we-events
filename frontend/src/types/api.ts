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
  article_count?: number;
}

export interface WechatAccountGroup {
  id: string;
  name: string;
  description?: string;
  status?: number;
  wechat_account_ids?: string[];
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
  source_wechat_account_id?: string;
  title: string;
  original_title?: string;
  registration_time_text?: string;
  registration_method?: string;
  event_time_text?: string;
  event_fee?: string;
  audience?: string;
  article_url?: string;
  status?: string;
  extraction_status?: string;
  fallback_reason?: string;
  confidence?: number;
  extracted_by?: string;
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
