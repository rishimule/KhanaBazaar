// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { ApiError, get, patch, post } from "@/lib/api";
import type {
  Campaign,
  CampaignAudienceCount,
  CampaignCreateInput,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BASE = "/api/v1/admin/notifications/campaigns";

export async function adminListCampaigns(token: string): Promise<Campaign[]> {
  return get<Campaign[]>(BASE, token);
}

export async function adminGetCampaign(id: number, token: string): Promise<Campaign> {
  return get<Campaign>(`${BASE}/${id}`, token);
}

export async function adminCreateCampaign(
  input: CampaignCreateInput,
  token: string,
): Promise<Campaign> {
  return post<Campaign>(BASE, input, token);
}

export async function adminUpdateCampaign(
  id: number,
  input: Partial<CampaignCreateInput>,
  token: string,
): Promise<Campaign> {
  return patch<Campaign>(`${BASE}/${id}`, input, token);
}

export async function adminCampaignAudienceCount(
  id: number,
  token: string,
): Promise<CampaignAudienceCount> {
  return post<CampaignAudienceCount>(`${BASE}/${id}/audience-count`, {}, token);
}

export async function adminSendCampaign(id: number, token: string): Promise<Campaign> {
  return post<Campaign>(`${BASE}/${id}/send`, {}, token);
}

/** Multipart image upload — uses fetch directly so the browser sets the
 *  multipart boundary (the shared `post` helper forces application/json). */
export async function uploadCampaignImage(
  id: number,
  file: File | Blob,
  token: string | null,
): Promise<Campaign> {
  const form = new FormData();
  form.append("file", file, "campaign.webp");
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${BASE}/${id}/image`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? res.statusText, res.status);
  }
  return res.json() as Promise<Campaign>;
}
