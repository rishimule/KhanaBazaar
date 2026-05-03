"use client";

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
  const [services, setServices] = useState<Service[] | null>(
    providedServices ?? null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // When a pre-fetched list is provided, keep local state in sync without
    // triggering a network request. State is initialised from props above so
    // this branch only runs when the prop changes after the first render.
    if (providedServices !== undefined) {
      return;
    }
    let cancelled = false;
    get<Service[]>("/api/v1/catalog/services", token ?? undefined)
      .then((rows) => {
        if (!cancelled) setServices(rows);
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
