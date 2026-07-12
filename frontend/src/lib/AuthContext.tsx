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
import { useRouter } from "next/navigation";
import { User, UserRole } from "@/types";
import { clearLocaleCookies, setOperatorLocaleCookie } from "@/lib/operatorLocale";
import { OPERATOR_PATH_RE } from "@/lib/localeCookies";
import { routing } from "@/i18n/routing";

/** For seller/admin sessions, seed the operator locale cookie (KB_OP_LOCALE)
 * from the persisted preference so a fresh device opens the dashboard in the
 * saved language. Returns whether the cookie value changed, so a stale server
 * render can be refreshed. Scoped to operator roles — customers keep their
 * URL-driven storefront locale, enforced by <CustomerLocaleEnforcer>. */
function reconcileOperatorLocale(user: User): boolean {
  if (typeof document === "undefined") return false;
  if (user.role !== "seller" && user.role !== "admin") return false;
  const lang = user.preferred_language;
  // Guard against a value the app can't render (defensive symmetry with
  // CustomerLocaleEnforcer); the read sites also fall back to the default.
  if (!lang || !routing.locales.includes(lang as (typeof routing.locales)[number])) {
    return false;
  }
  return setOperatorLocaleCookie(lang);
}

interface AuthContextValue {
  dbUser: User | null;
  token: string | null;
  loading: boolean;
  requestOtp: (email: string) => Promise<void>;
  verifyOtp: (
    email: string,
    code: string,
    fullName?: string,
    acceptPolicies?: boolean
  ) => Promise<{ user: User; needsName: boolean }>;
  logout: () => void;
  /** Record acceptance of the current policy version for the logged-in user,
   *  then clear the local needs_policy_acceptance flag (no /auth/me round-trip). */
  acceptPolicies: () => Promise<void>;
  /** Patch the cached user's avatar so the navbar + sidebars update instantly
   *  after a customer changes their picture (no /auth/me round-trip). */
  setAvatarUrl: (url: string | null) => void;
  /** Patch the cached user's language after a switch so the enforcer and
   *  seeding logic see the new preference without an /auth/me round-trip. */
  setPreferredLanguage: (locale: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "kb_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
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
          // If the operator cookie was stale (e.g. clobbered before the
          // isolation fix, or unset on a fresh device), refresh so the
          // already-rendered dashboard picks up the correct language.
          const changed = reconcileOperatorLocale(user);
          if (changed && OPERATOR_PATH_RE.test(window.location.pathname)) {
            router.refresh();
          }
        }
      })
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false));
  }, [router]);

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
      fullName?: string,
      acceptPolicies?: boolean
    ): Promise<{ user: User; needsName: boolean }> => {
      const res = await fetch(`${API_BASE}/api/v1/auth/otp/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          code,
          full_name: fullName ?? null,
          accept_policies: acceptPolicies ?? false,
        }),
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
      // Seed the operator cookie now; the post-login navigation into the
      // dashboard then server-renders in the saved language (no refresh here —
      // the login page itself is a customer route).
      reconcileOperatorLocale(data.user as User);
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
    // Clear the locale cookies so the next (guest) user on a shared device
    // isn't left on the previous user's language. Logged-in users re-seed from
    // their saved preference on the next auth resolution.
    clearLocaleCookies();
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

  const setAvatarUrl = useCallback((url: string | null) => {
    setDbUser((u) => (u ? { ...u, avatar_url: url } : u));
  }, []);

  const setPreferredLanguage = useCallback((locale: string) => {
    setDbUser((u) => (u ? { ...u, preferred_language: locale } : u));
  }, []);

  const acceptPolicies = useCallback(async () => {
    const stored =
      typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY);
    if (!stored) return;
    const res = await fetch(`${API_BASE}/api/v1/auth/policy/accept`, {
      method: "POST",
      headers: { Authorization: `Bearer ${stored}` },
    });
    if (!res.ok) throw new Error("Could not record acceptance.");
    setDbUser((u) => (u ? { ...u, needs_policy_acceptance: false } : u));
  }, []);

  const value = useMemo(
    () => ({
      dbUser,
      token,
      loading,
      requestOtp,
      verifyOtp,
      logout,
      acceptPolicies,
      setAvatarUrl,
      setPreferredLanguage,
    }),
    [
      dbUser,
      token,
      loading,
      requestOtp,
      verifyOtp,
      logout,
      acceptPolicies,
      setAvatarUrl,
      setPreferredLanguage,
    ]
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
