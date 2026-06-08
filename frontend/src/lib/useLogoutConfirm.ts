"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useCallback, useState } from "react";

/** Owns only the open/close state for a <LogoutConfirmDialog>. The dialog
 *  itself owns the confirm → logout → farewell → redirect lifecycle. */
export function useLogoutConfirm() {
  const [open, setOpen] = useState(false);
  const openDialog = useCallback(() => setOpen(true), []);
  const closeDialog = useCallback(() => setOpen(false), []);
  return { open, openDialog, closeDialog };
}
