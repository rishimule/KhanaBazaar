"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { use } from "react";
import AdminReturnsTable from "@/components/returns/AdminReturnsTable";

/**
 * Seller-scoped returns inside the supervisor hub. The hub layout already
 * renders the impersonation banner, so this is just the table.
 *
 * The hub's `id` param is the seller's User id, which is what
 * GET /admin/sellers/{seller_id}/returns expects.
 */
export default function AdminSellerReturnsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <AdminReturnsTable sellerUserId={Number(id)} />;
}
