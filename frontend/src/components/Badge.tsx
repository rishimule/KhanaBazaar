// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

export type BadgeKind =
  | "sale"
  | "new"
  | "hot"
  | "ebt"
  | "member"
  | "limited"
  | "local"
  | "instock"
  | "success"
  | "warning"
  | "neutral";

interface Props {
  kind?: BadgeKind;
  children: React.ReactNode;
  className?: string;
}

export default function Badge({ kind = "neutral", children, className = "" }: Props) {
  return (
    <span className={`badge badge--${kind} ${className}`.trim()}>
      {children}
    </span>
  );
}
