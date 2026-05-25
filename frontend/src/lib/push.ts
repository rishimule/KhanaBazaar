// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

/** Web Push browser helpers. All functions no-op gracefully when the
 *  browser lacks Push support or no VAPID key is configured. */

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** Convert a base64url VAPID public key to the Uint8Array applicationServerKey. */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

function extractKeys(sub: PushSubscription): { p256dh: string; auth: string } {
  const b64 = (buf: ArrayBuffer | null): string =>
    buf ? btoa(String.fromCharCode(...new Uint8Array(buf))) : "";
  return { p256dh: b64(sub.getKey("p256dh")), auth: b64(sub.getKey("auth")) };
}

/** Request permission + subscribe. Returns the subscription payload, or null
 *  if unsupported / denied / not configured. Caller POSTs it to the backend. */
export async function subscribeToPush(): Promise<{
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent: string;
} | null> {
  if (!pushSupported() || !VAPID_PUBLIC_KEY) return null;
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return null;
  const reg = await navigator.serviceWorker.ready;
  const existing = await reg.pushManager.getSubscription();
  const sub =
    existing ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      // Cast: the runtime value is a valid BufferSource; the TS DOM lib's
      // ArrayBuffer generic is stricter than the Uint8Array we build here.
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY) as BufferSource,
    }));
  return {
    endpoint: sub.endpoint,
    keys: extractKeys(sub),
    user_agent: navigator.userAgent,
  };
}

/** Unsubscribe in the browser. Returns the endpoint that was removed (so the
 *  caller can tell the backend), or null if there was nothing to remove. */
export async function unsubscribeFromPush(): Promise<string | null> {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return null;
  const { endpoint } = sub;
  await sub.unsubscribe();
  return endpoint;
}
