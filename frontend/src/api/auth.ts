import http from "@/api/http";
import type { CurrentUser } from "@/store/authStore";

export interface LoginParams {
  username: string;
  password: string;
}

export interface LoginResult {
  access_token: string;
  token_type: string;
  expires_in?: number;
  user?: CurrentUser;
}

export async function login(params: LoginParams): Promise<LoginResult> {
  const formData = new URLSearchParams();
  formData.append("username", params.username);
  formData.append("password", params.password);
  return http.post("/wx/auth/token", formData, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
}

export function verifyToken() {
  return http.get("/wx/auth/verify");
}

export function logout() {
  return http.post("/wx/auth/logout");
}

function normalizeQrUrl(url?: string): string {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    if (parsed.hostname === "host.docker.internal") {
      parsed.hostname = window.location.hostname || "localhost";
    }
    return parsed.toString();
  } catch {
    return url;
  }
}

function extractQrUrl(payload: any): string {
  return normalizeQrUrl(
    payload?.image_url ||
      payload?.code ||
      payload?.data?.image_url ||
      payload?.data?.code ||
      payload?.data?.wx_login_url ||
      ""
  );
}

export async function requestQrCode(): Promise<{ code: string; session_id?: string }> {
  const result: any = await http.get("/wx/auth/qr/code");
  return { code: extractQrUrl(result), session_id: result?.session_id };
}

export async function getQrUrl(): Promise<string> {
  const result: any = await http.get("/wx/auth/qr/url");
  return extractQrUrl(result);
}

export async function getQrStatus(): Promise<{ login_status: boolean }> {
  return http.get("/wx/auth/qr/status");
}

export function finishQr() {
  return http.get("/wx/auth/qr/over");
}
