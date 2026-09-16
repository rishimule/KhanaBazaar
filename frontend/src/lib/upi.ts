// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

/** Amount the customer actually transfers.
 *
 * `Order.total` is the GROSS goods cost; store credit is deducted from it
 * (and `Payment.amount` is also the gross, so never use that either).
 * Prefilling a UPI link with the gross would tell a customer holding ₹200 of
 * store credit to send the full amount — overpaying by exactly their balance.
 */
export function netPayable(order: {
  total: number;
  store_credit_applied?: number;
}): number {
  return Number((order.total - (order.store_credit_applied ?? 0)).toFixed(2));
}

/** Build a UPI intent URI. On Android this opens GPay/PhonePe/Paytm with the
 *  amount and an order reference already filled in. `tr` gives the seller a
 *  reconciliation handle in their bank statement. */
export function buildUpiUri(args: {
  vpa: string;
  payeeName: string;
  amount: number;
  orderId: number;
}): string {
  // Built with encodeURIComponent, NOT URLSearchParams: the latter encodes a
  // space as `+`, and UPI apps commonly render that literally — the customer
  // would see the payee as "Ganesh+Stores" and have no way to tell whether
  // that is the shop they meant to pay. encodeURIComponent yields %20.
  const params: [string, string][] = [
    ["pa", args.vpa],
    ["pn", args.payeeName],
    ["am", args.amount.toFixed(2)],
    ["cu", "INR"],
    ["tn", `Order #${args.orderId}`],
    ["tr", `KBORD${args.orderId}`],
  ];
  const query = params
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join("&");
  return `upi://pay?${query}`;
}

/** `upi://` intents do not fire reliably in iOS Safari, so iOS leads with the
 *  QR and copy-VPA instead of the app button. Best-effort UA sniff — a wrong
 *  answer only reorders the panel, it never blocks paying. */
export function isLikelyIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}
