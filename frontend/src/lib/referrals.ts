// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get, patch, post } from "./api";

export type ReferralStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "active"
  | "expired";
export type ReferralTargetRole = "customer" | "seller";

export interface Referral {
  id: number;
  source_user_id: number;
  source_role: "customer" | "seller" | "admin";
  target_role: ReferralTargetRole;
  invitee_name: string;
  invitee_phone: string | null;
  invitee_email: string | null;
  location_state: string;
  location_area: string;
  status: ReferralStatus;
  rejection_reason: string | null;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReferralInviteDetail {
  invitee_name: string;
  target_role: ReferralTargetRole;
  invitee_email: string | null;
  invitee_phone: string | null;
  expired: boolean;
  status: ReferralStatus;
}

export interface ReferralCreateInput {
  target_role: ReferralTargetRole;
  invitee_name: string;
  invitee_phone?: string;
  invitee_email?: string;
  location_state: string;
  location_area: string;
}

export interface ReferralSettings {
  require_admin_approval: boolean;
}

export interface AcceptResult {
  access_token: string;
  token_type: string;
  user: { id: number; email: string; role: string };
}

// ── Referrer (customer or seller) ────────────────────────────────────────
export const submitReferral = (token: string, input: ReferralCreateInput) =>
  post<Referral>("/api/v1/referrals", input, token);

export const listMyReferrals = (token: string, status?: ReferralStatus) =>
  get<Paged<Referral>>(
    status ? `/api/v1/referrals?status=${status}` : "/api/v1/referrals",
    token,
  );

// ── Public activation ────────────────────────────────────────────────────
export const getInvite = (inviteToken: string) =>
  get<ReferralInviteDetail>(
    `/api/v1/referrals/invite?token=${encodeURIComponent(inviteToken)}`,
  );

export const acceptCustomerReferral = (input: {
  token: string;
  code: string;
  email?: string;
  full_name?: string;
  accept_policies: boolean;
}) => post<AcceptResult>("/api/v1/referrals/accept", input);

// ── Admin ──────────────────────────────────────────────────────────────
export const adminListReferrals = (
  token: string,
  opts?: { status?: ReferralStatus; targetRole?: ReferralTargetRole; page?: number; pageSize?: number },
) => {
  const q = new URLSearchParams();
  if (opts?.status) q.set("status", opts.status);
  if (opts?.targetRole) q.set("target_role", opts.targetRole);
  if (opts?.page) q.set("page", String(opts.page));
  if (opts?.pageSize) q.set("page_size", String(opts.pageSize));
  const qs = q.toString();
  return get<Paged<Referral>>(`/api/v1/admin/referrals${qs ? `?${qs}` : ""}`, token);
};

export const adminApproveReferral = (token: string, id: number) =>
  post<Referral>(`/api/v1/admin/referrals/${id}/approve`, {}, token);

export const adminRejectReferral = (token: string, id: number, reason: string) =>
  post<Referral>(`/api/v1/admin/referrals/${id}/reject`, { reason }, token);

export const getReferralSettings = (token: string) =>
  get<ReferralSettings>("/api/v1/admin/referrals/settings", token);

export const patchReferralSettings = (token: string, require_admin_approval: boolean) =>
  patch<ReferralSettings>(
    "/api/v1/admin/referrals/settings",
    { require_admin_approval },
    token,
  );
