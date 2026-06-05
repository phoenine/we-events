import { create } from "zustand";
import { clearToken, getToken, setToken } from "@/utils/auth";

export interface CurrentUser {
  id: string;
  email: string;
  username: string;
  nickname?: string;
  role?: string;
  is_active?: boolean;
}

interface AuthState {
  token: string;
  user: CurrentUser | null;
  setAuth: (token: string, user?: CurrentUser | null) => void;
  setUser: (user: CurrentUser | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: getToken(),
  user: null,
  setAuth: (token, user = null) => {
    setToken(token);
    set({ token, user });
  },
  setUser: (user) => set({ user }),
  logout: () => {
    clearToken();
    set({ token: "", user: null });
  },
}));
