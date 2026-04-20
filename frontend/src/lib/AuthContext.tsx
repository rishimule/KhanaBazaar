"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { User, UserRole } from "@/types";

interface AuthContextValue {
  dbUser: User | null;
  token: string | null;
  loading: boolean;
  requestOtp: (email: string) => Promise<void>;
  verifyOtp: (
    email: string,
    code: string,
    fullName?: string
  ) => Promise<{ user: User; needsName: boolean }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "kb_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [dbUser, setDbUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((res) => {
        if (!res.ok) {
          localStorage.removeItem(TOKEN_KEY);
          return null;
        }
        return res.json() as Promise<User>;
      })
      .then((user) => {
        if (user) {
          setToken(stored);
          setDbUser(user);
        }
      })
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false));
  }, []);

  const requestOtp = useCallback(async (email: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/api/v1/auth/otp/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const detail = body?.detail;
      if (detail?.error === "rate_limited") {
        throw new Error(
          `Please wait ${detail.retry_after} seconds before requesting a new code.`
        );
      }
      throw new Error("Failed to send code. Please try again.");
    }
  }, []);

  const verifyOtp = useCallback(
    async (
      email: string,
      code: string,
      fullName?: string
    ): Promise<{ user: User; needsName: boolean }> => {
      const res = await fetch(`${API_BASE}/api/v1/auth/otp/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code, full_name: fullName ?? null }),
      });
      const data = await res.json();
      if (!res.ok) {
        const error = data?.detail?.error;
        if (error === "invalid_code")
          throw new Error("Incorrect code. Please try again.");
        if (error === "too_many_attempts")
          throw new Error("Too many attempts. Please request a new code.");
        if (error === "code_expired_or_used")
          throw new Error("Code expired. Please request a new one.");
        throw new Error("Verification failed.");
      }
      if (data.needs_name) {
        return { user: null as unknown as User, needsName: true };
      }
      localStorage.setItem(TOKEN_KEY, data.access_token);
      setToken(data.access_token);
      setDbUser(data.user as User);
      return { user: data.user as User, needsName: false };
    },
    []
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setDbUser(null);
  }, []);

  const value = useMemo(
    () => ({ dbUser, token, loading, requestOtp, verifyOtp, logout }),
    [dbUser, token, loading, requestOtp, verifyOtp, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

/** Hook to get a role-ready auth guard. Returns { authorized, loading, role }. */
export function useRequireRole(requiredRole: UserRole) {
  const { dbUser, loading } = useAuth();
  return {
    authorized: !loading && dbUser !== null && dbUser.role === requiredRole,
    loading,
    user: dbUser,
    role: dbUser?.role ?? null,
  };
}
