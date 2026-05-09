"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { Service } from "@/types";
import styles from "./ServicePicker.module.css";

interface Props {
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  token?: string | null;
  disabled?: boolean;
  /** Optional pre-fetched list. If provided, the component skips the internal fetch. */
  services?: Service[];
}

export default function ServicePicker({
  selectedIds,
  onChange,
  token,
  disabled = false,
  services: providedServices,
}: Props) {
  const [fetchedServices, setFetchedServices] = useState<Service[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const services = providedServices ?? fetchedServices;

  useEffect(() => {
    if (providedServices !== undefined) return;  // parent supplies the data
    let cancelled = false;
    get<Service[]>("/api/v1/catalog/services", token ?? undefined)
      .then((rows) => {
        if (!cancelled) setFetchedServices(rows);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message ?? "Failed to load services");
      });
    return () => {
      cancelled = true;
    };
  }, [token, providedServices]);

  if (error) {
    return <p className={styles.error}>{error}</p>;
  }
  if (services === null) {
    return (
      <div className={styles.grid}>
        {[1, 2, 3].map((n) => (
          <div key={n} className={styles.skeleton} />
        ))}
      </div>
    );
  }

  function toggle(id: number) {
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter((s) => s !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  }

  return (
    <div className={styles.grid} role="group" aria-label="Services offered">
      {services.map((service) => {
        const checked = selectedIds.includes(service.id);
        return (
          <label
            key={service.id}
            className={`${styles.card} ${checked ? styles.cardChecked : ""}`}
          >
            <input
              type="checkbox"
              className={styles.checkbox}
              checked={checked}
              disabled={disabled}
              onChange={() => toggle(service.id)}
            />
            <span className={styles.name}>{service.name}</span>
            {service.description && (
              <span className={styles.description}>{service.description}</span>
            )}
          </label>
        );
      })}
    </div>
  );
}
