"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

export default function IOSInstallSheet({ onClose }: { onClose: () => void }) {
  // Real implementation lands in Task 4.
  return (
    <div role="dialog" aria-modal="true">
      <button type="button" onClick={onClose}>close</button>
    </div>
  );
}
