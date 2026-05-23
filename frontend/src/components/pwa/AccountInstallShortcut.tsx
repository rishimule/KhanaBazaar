"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.

import { useTranslations } from "next-intl";
import { usePWAInstall } from "./usePWAInstall";

type Props = {
  shortcutClassName: string;
  iconClassName: string;
  labelClassName: string;
};

export default function AccountInstallShortcut({
  shortcutClassName,
  iconClassName,
  labelClassName,
}: Props) {
  const t = useTranslations("Account.dashboard");
  const { canShowEntry, install } = usePWAInstall();

  if (!canShowEntry) return null;

  return (
    <button
      type="button"
      className={shortcutClassName}
      style={{ font: "inherit", appearance: "none" }}
      onClick={() => install("account_shortcut")}
    >
      <span className={iconClassName} aria-hidden="true">📲</span>
      <span className={labelClassName}>{t("shortcutInstallApp")}</span>
    </button>
  );
}
