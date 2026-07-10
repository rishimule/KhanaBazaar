// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get, patch, post } from "@/lib/api";

export type CreditStatus = "active" | "suspended";
export type CreditEntryType = "charge" | "repayment" | "reversal";

export interface CreditAccount {
  id: number;
  customer_profile_id: number;
  seller_profile_id: number;
  credit_limit: number;
  outstanding_balance: number;
  available: number;
  status: CreditStatus;
  created_at: string;
}

export interface CreditLedgerEntry {
  id: number;
  entry_type: CreditEntryType;
  amount: number;
  order_id: number | null;
  balance_after: number;
  note: string | null;
  created_at: string;
}

export interface CustomerCreditAccount {
  seller_profile_id: number;
  store_name: string;
  credit_limit: number;
  outstanding_balance: number;
  available: number;
  status: CreditStatus;
}

export interface CreditEligibility {
  eligible: boolean;
  available: number;
  credit_limit: number;
  outstanding_balance: number;
}

export interface SellerCreditConfig {
  credit_enabled: boolean;
  max_limit_per_customer: number;
}

interface PagedLedger {
  items: CreditLedgerEntry[];
  total: number;
  page: number;
  page_size: number;
}

// ── Seller ───────────────────────────────────────────────────────────────
export const getSellerCreditConfig = (token: string) =>
  get<SellerCreditConfig>("/api/v1/credit/config", token);

export const listSellerCreditAccounts = (token: string) =>
  get<CreditAccount[]>("/api/v1/credit/accounts", token);

export const grantCredit = (
  token: string,
  body: { customer_phone?: string; customer_email?: string; credit_limit: number },
) => post<CreditAccount>("/api/v1/credit/accounts", body, token);

export const patchCreditAccount = (
  token: string,
  id: number,
  body: { credit_limit?: number; status?: CreditStatus },
) => patch<CreditAccount>(`/api/v1/credit/accounts/${id}`, body, token);

export const recordRepayment = (
  token: string,
  id: number,
  body: { amount: number; note?: string },
) => post<CreditLedgerEntry>(`/api/v1/credit/accounts/${id}/repayments`, body, token);

export const getCreditLedger = (token: string, id: number) =>
  get<PagedLedger>(`/api/v1/credit/accounts/${id}/ledger`, token);

// ── Customer ─────────────────────────────────────────────────────────────
export const getMyCredit = (token: string) =>
  get<CustomerCreditAccount[]>("/api/v1/customers/me/credit", token);

export const getCreditEligibility = (token: string, storeId: number, total: number) =>
  get<CreditEligibility>(
    `/api/v1/customers/me/credit/eligibility?store_id=${storeId}&total=${total}`,
    token,
  );

// ── Admin ────────────────────────────────────────────────────────────────
export const getAdminCreditConfig = (token: string, sellerId: number) =>
  get<SellerCreditConfig>(`/api/v1/admin/sellers/${sellerId}/credit-config`, token);

export const patchAdminCreditConfig = (
  token: string,
  sellerId: number,
  body: Partial<SellerCreditConfig>,
) => patch<SellerCreditConfig>(`/api/v1/admin/sellers/${sellerId}/credit-config`, body, token);
