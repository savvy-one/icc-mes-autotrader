import { create } from "zustand";

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function setCookie(name: string, value: string, days: number) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

function deleteCookie(name: string) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
}

interface AuthState {
  token: string | null;
  user: string | null;
  isAuthenticated: boolean;
  login: (token: string, user: string) => void;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,

  login: (token, user) => {
    setCookie("icc_token", token, 1);
    set({ token, user, isAuthenticated: true });
  },

  logout: () => {
    deleteCookie("icc_token");
    set({ token: null, user: null, isAuthenticated: false });
    window.location.href = "/login";
  },

  hydrate: () => {
    const token = getCookie("icc_token");
    if (token) {
      set({ token, isAuthenticated: true });
    }
  },
}));
