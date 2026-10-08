// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { PaymentMethod } from "@/types";

export type LocalMode = "door_delivery" | "pickup";

/** Store methods each local delivery mode can offer, in display order —
 *  mirrors backend `services/payment_methods.MODE_METHODS`. */
export const LOCAL_MODE_METHODS: Record<LocalMode, PaymentMethod[]> = {
  door_delivery: ["upi", "net_banking", "cash"],
  pickup: ["upi", "net_banking", "pay_at_store"],
};

/** The order checkout falls back through when the chosen method is not live. */
export const FALLBACK_ORDER: Record<LocalMode, PaymentMethod[]> = {
  door_delivery: ["upi", "cash", "net_banking"],
  pickup: ["upi", "pay_at_store", "net_banking"],
};

/** Methods this store takes for a local mode. `undefined` while the store
 *  payload is loading — never confuse that with "takes nothing" (`[]`). */
export function localMethodsFor(
  accepted: PaymentMethod[] | undefined,
  mode: LocalMode,
): PaymentMethod[] | undefined {
  if (accepted === undefined) return undefined;
  return LOCAL_MODE_METHODS[mode].filter((m) => accepted.includes(m));
}
