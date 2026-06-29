// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { get, patch, post } from "@/lib/api";
import type {
  OnboardingRequestStatus,
  PagedResponse,
  SellerOnboardingRequest,
  SellerOnboardingRequestCreate,
} from "@/types";

/** Public lead capture — works for guests and logged-in users. */
export function submitOnboardingRequest(payload: SellerOnboardingRequestCreate) {
  return post<SellerOnboardingRequest>(
    "/api/v1/seller-onboarding-requests",
    payload,
  );
}

/** Admin: paginated list of onboarding leads. */
export function adminListOnboardingRequests(
  params: { status: string; q: string; page: number; pageSize: number },
  token: string,
) {
  const qs = new URLSearchParams({
    status: params.status,
    page: String(params.page),
    page_size: String(params.pageSize),
  });
  if (params.q) qs.set("q", params.q);
  return get<PagedResponse<SellerOnboardingRequest>>(
    `/api/v1/admin/onboarding-requests?${qs.toString()}`,
    token,
  );
}

/** Admin: update a lead's lifecycle status. */
export function adminUpdateOnboardingStatus(
  id: number,
  status: OnboardingRequestStatus,
  token: string,
) {
  return patch<SellerOnboardingRequest>(
    `/api/v1/admin/onboarding-requests/${id}`,
    { status },
    token,
  );
}
