// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
const KEY = "kb_dev_inbox_auth";

export function getCreds(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(KEY);
}

export function setCreds(user: string, pass: string): void {
  sessionStorage.setItem(KEY, btoa(`${user}:${pass}`));
}

export function clearCreds(): void {
  sessionStorage.removeItem(KEY);
}

export function authHeader(basic: string): HeadersInit {
  return { Authorization: `Basic ${basic}` };
}
