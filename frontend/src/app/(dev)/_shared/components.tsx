// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"use client";
import Link from "next/link";
import { useState } from "react";

import styles from "./inbox.module.css";
import { useLogin } from "./useInbox";

export function LoginGate({ onAuthed }: { onAuthed: () => void }) {
  const { attempt, err } = useLogin(onAuthed);
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  return (
    <form
      className={styles.login}
      onSubmit={(e) => {
        e.preventDefault();
        void attempt(user, pass);
      }}
    >
      <h1>Dev Mailbox</h1>
      <input
        placeholder="Username"
        value={user}
        onChange={(e) => setUser(e.target.value)}
        autoComplete="username"
      />
      <input
        placeholder="Password"
        type="password"
        value={pass}
        onChange={(e) => setPass(e.target.value)}
        autoComplete="current-password"
      />
      <button type="submit">Sign in</button>
      {err && <div className={styles.error}>{err}</div>}
    </form>
  );
}

export function InboxHeader({
  title,
  onLogout,
}: {
  title: string;
  onLogout: () => void;
}) {
  return (
    <div className={styles.header}>
      <h1>{title}</h1>
      <nav className={styles.nav}>
        <Link href="/dev-emails">Emails</Link>
        <Link href="/dev-sms">SMS</Link>
        <Link href="/dev-whatsapp">WhatsApp</Link>
        <button type="button" onClick={onLogout}>
          Logout
        </button>
      </nav>
    </div>
  );
}

export function SearchBar({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <input
      className={styles.search}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function NewMessagesBanner({
  count,
  onClick,
}: {
  count: number;
  onClick: () => void;
}) {
  if (count <= 0) return null;
  return (
    <div className={styles.banner} onClick={onClick}>
      {count} new message{count === 1 ? "" : "s"} — click to load
    </div>
  );
}

export function Pager({
  page,
  pageSize,
  total,
  onPage,
  onRefresh,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
  onRefresh: () => void;
}) {
  const maxPage = Math.max(0, Math.ceil(total / pageSize) - 1);
  return (
    <div className={styles.pager}>
      <button disabled={page <= 0} onClick={() => onPage(page - 1)}>
        ← Prev
      </button>
      <span className={styles.muted}>
        Page {page + 1} of {maxPage + 1} · {total} total
      </span>
      <button disabled={page >= maxPage} onClick={() => onPage(page + 1)}>
        Next →
      </button>
      <button onClick={onRefresh}>Refresh</button>
    </div>
  );
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString();
}
