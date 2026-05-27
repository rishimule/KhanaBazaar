"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { User, UserRole } from "@/types";
import { setLocaleCookie } from "@/lib/operatorLocale";

/** For seller/admin sessions, seed the NEXT_LOCALE cookie from the persisted
 * preference so a fresh device opens the dashboard in the saved language.
 * Scoped to operator roles — customers keep their URL-driven storefront locale. */
function seedOperatorLocale(user: User): void {
  if (typeof document === "undefined") return;
  if (user.role !== "seller" && user.role !== "admin") return;
  if (user.preferred_language) setLocaleCookie(user.preferred_language);
}

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
  // Always start loading=true so server and client first render agree.
  // The useEffect below flips it to false once we know whether a token exists
  // (and after /auth/me resolves if it does). Reading localStorage in the
  // useState initializer caused a hydration mismatch — server saw no
  // localStorage, client saw the missing token and rendered with loading=false.
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const stored =
      typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY);
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
          seedOperatorLocale(user);
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
      seedOperatorLocale(data.user as User);
      return { user: data.user as User, needsName: false };
    },
    []
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    // Wipe the per-session "deliver to" pick so the next user on a shared
    // device doesn't inherit the previous user's location. Inlined rather
    // than calling DeliveryLocationContext.clearStoredDeliveryLocation()
    // because DeliveryLocationContext now imports useAuth, and importing
    // back here would create a circular module dependency that breaks
    // Next.js HMR.
    localStorage.removeItem("kb_delivery_location");
    // Wipe recent search history for the same reason.
    localStorage.removeItem("kb_recent_searches");
    // Tear down web-push on this device so the next user on a shared device
    // never inherits the prior customer's order alerts. Fire-and-forget so the
    // logout signature stays synchronous. Dynamic-imported to avoid pulling the
    // push/notifications modules into the auth bundle.
    const tokenForTeardown = token;
    void (async () => {
      try {
        const { unsubscribeFromPush } = await import("@/lib/push");
        const { unsubscribePush } = await import("@/lib/notifications");
        const endpoint = await unsubscribeFromPush();
        if (endpoint && tokenForTeardown) {
          await unsubscribePush(tokenForTeardown, endpoint);
        }
      } catch {
        /* best-effort */
      }
    })();
    setToken(null);
    setDbUser(null);
  }, [token]);

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
