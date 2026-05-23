// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

/**
 * Chromium-only event fired before the browser shows its native install prompt.
 * Not in the TypeScript DOM lib. See:
 * https://developer.mozilla.org/en-US/docs/Web/API/BeforeInstallPromptEvent
 */
export interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  readonly userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
  prompt(): Promise<void>;
}

export type PwaPlatform = "android" | "ios" | "other";
