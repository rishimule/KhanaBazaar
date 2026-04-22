import type { Address } from "@/types";

export function formatAddress(addr: Address): string {
  const parts: string[] = [addr.address_line1];
  if (addr.address_line2 && addr.address_line2.trim()) parts.push(addr.address_line2.trim());
  if (addr.landmark && addr.landmark.trim()) parts.push(addr.landmark.trim());
  parts.push(addr.city);
  parts.push(`${addr.state} ${addr.pincode}`);
  parts.push(addr.country);
  return parts.join(", ");
}
