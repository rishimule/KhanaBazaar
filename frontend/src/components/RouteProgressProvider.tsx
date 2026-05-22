// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"use client";

import { ProgressProvider } from "@bprogress/next/app";

import type { ReactNode } from "react";

export default function RouteProgressProvider({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <ProgressProvider
      height="2px"
      color="var(--color-primary)"
      options={{ showSpinner: false }}
      shallowRouting
      delay={150}
    >
      {children}
    </ProgressProvider>
  );
}
