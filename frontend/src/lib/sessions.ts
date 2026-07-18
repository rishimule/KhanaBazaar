// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get, del, post } from "@/lib/api";

export interface DeviceSession {
  id: number;
  device_label: string;
  ip: string | null;
  trusted: boolean;
  created_at: string;
  last_used_at: string;
  current: boolean;
}

export function listSessions(token: string): Promise<DeviceSession[]> {
  return get<DeviceSession[]>("/api/v1/auth/sessions", token);
}

export function revokeSession(token: string, id: number): Promise<void> {
  return del<void>(`/api/v1/auth/sessions/${id}`, token);
}

export function revokeAllSessions(token: string): Promise<{ revoked: number }> {
  return post<{ revoked: number }>(
    "/api/v1/auth/sessions/revoke-all",
    undefined,
    token,
  );
}
