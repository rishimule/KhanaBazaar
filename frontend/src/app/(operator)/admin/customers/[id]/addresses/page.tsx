"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/AuthContext";
import { fetchCustomerAddresses } from "@/lib/adminCustomers";
import { formatAddress } from "@/lib/format-address";
import type { CustomerAddress } from "@/types";
import styles from "../tabs.module.css";

export default function CustomerAddressesTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.customers");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const [addresses, setAddresses] = useState<CustomerAddress[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setAddresses(await fetchCustomerAddresses(Number(id), token));
    } catch {
      setError(true);
    }
  }, [id, token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load sets state inside async callbacks
    load();
  }, [load]);

  if (error) return <div className={styles.errorBox}>{t("addresses.loadError")}</div>;
  if (!addresses) return <div className={styles.state}>{tc("loading")}</div>;

  return (
    <div>
      <h2 className={styles.heading}>
        {t("addresses.heading", { n: addresses.length })}
      </h2>
      {addresses.length === 0 ? (
        <div className={styles.empty}>{t("addresses.empty")}</div>
      ) : (
        <div className={styles.addressGrid}>
          {addresses.map((a) => (
            <div key={a.id} className={styles.addressCard}>
              <div className={styles.addressLabelRow}>
                <span className={styles.addressLabel}>
                  {a.label || t("addresses.unlabeled")}
                </span>
                {a.is_default && (
                  <span className={styles.defaultBadge}>
                    {t("addresses.default")}
                  </span>
                )}
              </div>
              <div className={styles.addressBody}>{formatAddress(a.address)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
