// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get, post } from "@/lib/api";
import type { NotificationListResponse } from "@/types";

export async function listNotifications(
  token: string
): Promise<NotificationListResponse> {
  return get<NotificationListResponse>("/api/v1/notifications", token);
}

export async function markNotificationRead(
  token: string,
  id: number
): Promise<void> {
  await post(`/api/v1/notifications/${id}/read`, undefined, token);
}

export async function markAllNotificationsRead(token: string): Promise<void> {
  await post("/api/v1/notifications/read-all", undefined, token);
}

export interface PushSubscriptionPayload {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent?: string;
}

export async function subscribePush(
  token: string,
  payload: PushSubscriptionPayload
): Promise<void> {
  await post("/api/v1/notifications/push/subscribe", payload, token);
}

export async function unsubscribePush(
  token: string,
  endpoint: string
): Promise<void> {
  await post("/api/v1/notifications/push/unsubscribe", { endpoint }, token);
}
