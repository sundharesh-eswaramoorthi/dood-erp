import { create } from "zustand";

import { api } from "../lib/api";

export interface UserInfo {
  id: number;
  username: string;
  full_name: string | null;
  org_id: number;
  branch_ids: number[];
  perms: string[];
}

interface AuthState {
  user: UserInfo | null;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

function storedUser(): UserInfo | null {
  try {
    return JSON.parse(localStorage.getItem("user") || "null");
  } catch {
    return null;
  }
}

export const useAuth = create<AuthState>((set) => ({
  user: storedUser(),
  token: localStorage.getItem("access_token"),
  login: async (username, password) => {
    const body = new URLSearchParams({ username, password });
    const { data } = await api.post("/api/v1/auth/login", body, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    localStorage.setItem("user", JSON.stringify(data.user));
    set({ user: data.user, token: data.access_token });
  },
  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
    set({ user: null, token: null });
  },
}));
