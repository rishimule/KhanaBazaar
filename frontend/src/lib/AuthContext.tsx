"use client";

/**
 * Khana Bazaar — Auth Context
 *
 * Provides Firebase authentication state and user role information
 * to the entire application. Handles login, logout, and token management.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
  type User as FirebaseUser,
} from "firebase/auth";
import { firebaseAuth } from "@/lib/firebase";
import { User, UserRole } from "@/types";

interface AuthContextValue {
  /** Firebase user object — null when logged out */
  firebaseUser: FirebaseUser | null;
  /** Backend user object with role — null when not yet fetched */
  dbUser: User | null;
  /** Current Firebase ID token for API calls */
  token: string | null;
  /** True while initial auth state is being resolved */
  loading: boolean;
  /** Sign in with email + password, returns the backend user */
  login: (email: string, password: string) => Promise<User>;
  /** Sign out */
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [dbUser, setDbUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Fetch the backend user using a token
  const fetchDbUser = useCallback(async (idToken: string): Promise<User> => {
    const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${idToken}`,
      },
    });
    if (!res.ok) {
      throw new Error("Failed to fetch user from backend");
    }
    return (await res.json()) as User;
  }, []);

  // Listen for auth state changes
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(firebaseAuth, async (user) => {
      if (user) {
        try {
          const idToken = await user.getIdToken();
          setFirebaseUser(user);
          setToken(idToken);
          const backendUser = await fetchDbUser(idToken);
          setDbUser(backendUser);
        } catch (err) {
          console.error("Auth state error:", err);
          setFirebaseUser(null);
          setDbUser(null);
          setToken(null);
        }
      } else {
        setFirebaseUser(null);
        setDbUser(null);
        setToken(null);
      }
      setLoading(false);
    });
    return unsubscribe;
  }, [fetchDbUser]);

  const login = useCallback(
    async (email: string, password: string): Promise<User> => {
      const credential = await signInWithEmailAndPassword(
        firebaseAuth,
        email,
        password
      );
      const idToken = await credential.user.getIdToken();
      setFirebaseUser(credential.user);
      setToken(idToken);
      const backendUser = await fetchDbUser(idToken);
      setDbUser(backendUser);
      return backendUser;
    },
    [fetchDbUser]
  );

  const logout = useCallback(async () => {
    await signOut(firebaseAuth);
    setFirebaseUser(null);
    setDbUser(null);
    setToken(null);
  }, []);

  const value = useMemo(
    () => ({ firebaseUser, dbUser, token, loading, login, logout }),
    [firebaseUser, dbUser, token, loading, login, logout]
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
