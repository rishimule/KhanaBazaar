"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SellerHubRoot({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  useEffect(() => {
    router.replace(`/admin/sellers/${id}/products`);
  }, [id, router]);
  return null;
}
