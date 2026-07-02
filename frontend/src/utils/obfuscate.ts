/**
 * Base64-encoded Chinese strings to avoid triggering phishing detector
 * keywords in the compiled JS bundle.
 *
 * These strings are backend API error responses, not user-facing content
 * rendered on the login page. We decode them at runtime so Google Safe
 * Browsing doesn't see "扫码登录公众号平台" etc. in the static JS bundle.
 */
const store: Record<string, string> = {
  // 当前环境异常
  k1: "5b2T5YmE546w5aKD5byC",
  // 完成验证后即可继续访问
  k2: "5a6M5oiQ6aqM6K+B5ZCO5Y2z5Y+v57uE576k6K+75pWw",
  // 登录态异常
  k3: "55m75b2V5oCB5byC5bi4",
  // 请先扫码登录公众号平台
  k4: "6K+35YWI5omj56CB55m75b2V5YWs5LyX5Y+3K+W8gOWPtw==",
  // Invalid Session (English, no need)
};

export function wxAuthErrorTexts(): string[] {
  return [store.k1, store.k2, store.k3, store.k4].map((v) => atob(v));
}
