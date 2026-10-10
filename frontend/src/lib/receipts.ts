// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get } from "@/lib/api";
import type { Receipt, ReceiptSnapshot } from "@/types";

export function getOrderReceipt(token: string, orderId: number): Promise<Receipt> {
  return get<Receipt>(`/api/v1/orders/${orderId}/receipt`, token);
}

export type ReceiptPaymentKey = "paidWithStoreCredit" | "paid" | "onCredit" | "unpaid";

/** Which `Receipt.payment.*` message says how the order was paid. Same rule
 *  order as the email's `services/receipts.payment_line`; keep in step. */
export function receiptPaymentKey(s: ReceiptSnapshot): ReceiptPaymentKey {
  if (s.payment.settled === "unpaid") return "unpaid";
  // Before the credit line: store credit can cover a postpaid order whole.
  if (s.amounts.amount_paid === 0 && s.amounts.store_credit_applied > 0) {
    return "paidWithStoreCredit";
  }
  if (s.payment.settled === "on_credit") return "onCredit";
  return "paid";
}

/** Always IST: next-intl's formatter renders in the server's zone, which is
 *  UTC on Cloud Run, so a 23:30 IST delivery would print as the wrong day.
 *  Latin digits in every language (Marathi would otherwise use Devanagari),
 *  so dates match the amounts and receipt number beside them. */
export function formatReceiptDate(iso: string, locale: string, withTime = true): string {
  return new Date(iso).toLocaleString(`${locale}-IN-u-nu-latn`, {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "numeric", minute: "2-digit" } : {}),
  });
}

export function money(amount: number): string {
  return amount.toFixed(2);
}
