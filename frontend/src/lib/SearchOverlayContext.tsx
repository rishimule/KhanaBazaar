"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type SearchOverlayContextValue = {
  open: boolean;
  setOpen: (value: boolean) => void;
};

const SearchOverlayContext = createContext<SearchOverlayContextValue>({
  open: false,
  setOpen: () => {},
});

export function useSearchOverlay(): SearchOverlayContextValue {
  return useContext(SearchOverlayContext);
}

export function SearchOverlayProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const value = useMemo(() => ({ open, setOpen }), [open]);
  return (
    <SearchOverlayContext.Provider value={value}>
      {children}
    </SearchOverlayContext.Provider>
  );
}
