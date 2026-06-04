// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { useCallback, useEffect, useState } from "react";

interface OtpEntry {
  to: string;
  code: string;
  purpose: string;
  ts: string;
}

const STORAGE_KEY = "kb_devlogs_basic";

export default function DevLogsPage() {
  const [authHeader, setAuthHeader] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return sessionStorage.getItem(STORAGE_KEY);
  });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otps, setOtps] = useState<OtpEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const poll = useCallback(async (header: string) => {
    try {
      const resp = await fetch("/api/v1/dev/otps", {
        headers: { Authorization: header },
      });
      if (resp.status === 401) {
        setError("Invalid credentials");
        setAuthHeader(null);
        sessionStorage.removeItem(STORAGE_KEY);
        return;
      }
      if (resp.status === 404) {
        setError("Dev OTP inbox is disabled on this server.");
        return;
      }
      if (!resp.ok) {
        setError(`Error ${resp.status}`);
        return;
      }
      const body = await resp.json();
      setOtps(body.otps ?? []);
      setError(null);
    } catch {
      setError("Network error");
    }
  }, []);

  useEffect(() => {
    if (!authHeader) return;
    // poll() only setStates after an awaited fetch (not synchronous), so this
    // does not cause the cascading renders the rule guards against.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    poll(authHeader);
    const id = setInterval(() => poll(authHeader), 5000);
    return () => clearInterval(id);
  }, [authHeader, poll]);

  function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    const header = "Basic " + btoa(`${username}:${password}`);
    sessionStorage.setItem(STORAGE_KEY, header);
    setAuthHeader(header);
  }

  if (!authHeader) {
    return (
      <main style={{ maxWidth: 360, margin: "80px auto", fontFamily: "system-ui" }}>
        <h1 style={{ fontSize: 20 }}>Dev OTP inbox</h1>
        <form onSubmit={handleLogin} style={{ display: "grid", gap: 8 }}>
          <input
            placeholder="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
          <input
            placeholder="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <button type="submit">Sign in</button>
        </form>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </main>
    );
  }

  return (
    <main style={{ maxWidth: 720, margin: "40px auto", fontFamily: "system-ui" }}>
      <h1 style={{ fontSize: 20 }}>Dev OTP inbox</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <p style={{ color: "#666", fontSize: 13 }}>Auto-refreshing every 5s. Newest first.</p>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
            <th>Recipient</th>
            <th>Code</th>
            <th>Purpose</th>
            <th>Time (UTC)</th>
          </tr>
        </thead>
        <tbody>
          {otps.map((o, i) => (
            <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
              <td>{o.to}</td>
              <td style={{ fontFamily: "monospace", fontWeight: 700 }}>{o.code}</td>
              <td>{o.purpose}</td>
              <td>{o.ts}</td>
            </tr>
          ))}
          {otps.length === 0 && (
            <tr>
              <td colSpan={4} style={{ color: "#999", padding: "12px 0" }}>
                No codes yet — request an OTP, then watch here.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
