import http from "@/api/http";
import type { CurrentUser } from "@/store/authStore";

export interface UpdateUserPayload {
  username?: string;
  nickname?: string;
  email?: string;
  is_active?: boolean;
}

export function getCurrentUser(): Promise<CurrentUser> {
  return http.get("/wx/user");
}

export function updateUser(payload: UpdateUserPayload) {
  return http.put("/wx/user", payload);
}

export function changePassword(payload: { old_password: string; new_password: string }) {
  return http.put("/wx/user/password", payload);
}
