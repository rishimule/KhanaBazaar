// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { ReactNode } from "react";

export default function StoreLayout({
  children,
  modal,
}: {
  children: ReactNode;
  modal: ReactNode;
}) {
  return (
    <>
      {children}
      {modal}
    </>
  );
}
