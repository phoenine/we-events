import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { App } from "antd";
import { clearToken, getToken } from "@/utils/auth";
import { wxAuthErrorTexts } from "@/utils/obfuscate";

export const WX_AUTH_HINT_EVENT = "wx-auth-required";

function extractErrorText(payload: unknown): string {
  const data = payload as any;
  if (!data) return "";
  if (typeof data === "string") return data;
  if (typeof data?.message === "string") return data.message;
  if (typeof data?.detail === "string") return data.detail;
  if (typeof data?.detail?.message === "string") return data.detail.message;
  return "";
}

function isWechatAuthError(text: string): boolean {
  return [...wxAuthErrorTexts(), "Invalid Session"].some((item) =>
    text.includes(item),
  );
}

function notifyWechatAuthRequired(reason: string) {
  window.dispatchEvent(new CustomEvent(WX_AUTH_HINT_EVENT, { detail: { reason } }));
}

export const http = axios.create({
  baseURL: "/api/v1",
  timeout: 100_000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => {
    const data = response.data;
    if (response.status >= 200 && response.status < 300 && data?.code === undefined) {
      return data;
    }
    if (data?.code === 0) {
      return data?.data ?? data?.detail ?? data;
    }
    if (data?.code === 401) {
      clearToken();
      window.location.assign("/login");
      return Promise.reject(new Error("未登录或登录已过期，请重新登录。"));
    }
    const payload = data?.detail || data;
    const message = extractErrorText(payload) || "请求失败";
    if (isWechatAuthError(message)) {
      notifyWechatAuthRequired(message);
    }
    return Promise.reject(new Error(message));
  },
  (error: AxiosError) => {
    const status = error.response?.status;
    const data = error.response?.data as any;
    const message =
      extractErrorText(data) ||
      extractErrorText(data?.detail) ||
      error.message ||
      "请求错误";
    if (status === 401) {
      clearToken();
      window.location.assign("/login");
    }
    if (isWechatAuthError(message)) {
      notifyWechatAuthRequired(message);
    }
    return Promise.reject(new Error(message));
  }
);

export function useMessageApi() {
  return App.useApp().message;
}

export default http;
