"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import styles from "./page.module.css";

const TEST_ACCOUNTS = [
  { email: "admin@khanabazaar.dev", password: "Test@12345", role: "Admin", icon: "⚙️" },
  { email: "seller@khanabazaar.dev", password: "Test@12345", role: "Seller", icon: "🏪" },
  { email: "customer@khanabazaar.dev", password: "Test@12345", role: "Customer", icon: "🛒" },
];

export default function LoginPage() {
  const router = useRouter();
  const { login, dbUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // If already logged in, redirect
  if (dbUser) {
    const dest =
      dbUser.role === "admin" ? "/admin" :
      dbUser.role === "seller" ? "/seller" :
      "/stores";
    router.push(dest);
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(email, password);
      const dest =
        user.role === "admin" ? "/admin" :
        user.role === "seller" ? "/seller" :
        "/stores";
      router.push(dest);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed";
      if (msg.includes("auth/invalid-credential") || msg.includes("auth/wrong-password")) {
        setError("Invalid email or password.");
      } else if (msg.includes("auth/user-not-found")) {
        setError("No account found with this email.");
      } else if (msg.includes("auth/invalid-email")) {
        setError("Invalid email format.");
      } else {
        setError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleTestLogin = async (account: typeof TEST_ACCOUNTS[0]) => {
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(account.email, account.password);
      const dest =
        user.role === "admin" ? "/admin" :
        user.role === "seller" ? "/seller" :
        "/stores";
      router.push(dest);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.cardLogo}>🛍️</div>
          <h1 className={styles.cardTitle}>
            Welcome to <span className={styles.cardTitleAccent}>KhanaBazaar</span>
          </h1>
          <p className={styles.cardSubtitle}>
            Sign in to start shopping from local stores
          </p>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          {error && <div className={styles.error}>{error}</div>}

          <div className={styles.inputGroup}>
            <label className={styles.label} htmlFor="login-email">Email</label>
            <input
              id="login-email"
              className={styles.input}
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>

          <div className={styles.inputGroup}>
            <label className={styles.label} htmlFor="login-password">Password</label>
            <input
              id="login-password"
              className={styles.input}
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>

          <button
            type="submit"
            className={styles.submitBtn}
            disabled={submitting}
          >
            {submitting ? "Signing in…" : "Sign In"}
          </button>

          <div className={styles.divider}>Quick Login (Test Accounts)</div>

          <div className={styles.testAccounts}>
            {TEST_ACCOUNTS.map((acc) => (
              <button
                key={acc.email}
                type="button"
                className={styles.testBtn}
                onClick={() => handleTestLogin(acc)}
                disabled={submitting}
              >
                <span className={styles.testBtnIcon}>{acc.icon}</span>
                <span className={styles.testBtnInfo}>
                  <span className={styles.testBtnRole}>{acc.role}</span>
                  <span className={styles.testBtnEmail}>{acc.email}</span>
                </span>
              </button>
            ))}
          </div>
        </form>
      </div>
    </div>
  );
}
