"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useState } from "react";

import Modal from "@/components/Modal";
import { AddressAutocomplete } from "@/components/AddressAutocomplete";
import { MapPicker } from "@/components/MapPicker";
import {
  truncateLabel,
  type GeoPlace,
} from "@/lib/geo";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { useCustomerAddresses } from "@/lib/CustomerAddressesContext";
import { useAuth } from "@/lib/AuthContext";
import { formatAddress } from "@/lib/format-address";
import type { CustomerAddress } from "@/types";

import styles from "./DeliveryLocationPicker.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function DeliveryLocationPicker({ open, onClose }: Props) {
  const { setLocation } = useDeliveryLocation();
  const auth = useAuth();
  const { addresses } = useCustomerAddresses();

  const savedRows: CustomerAddress[] =
    auth.dbUser?.role === "customer"
      ? addresses.filter(
          (a) => a.address.latitude != null && a.address.longitude != null,
        )
      : [];

  const [staged, setStaged] = useState<{
    lat: number; lng: number; label: string;
  } | null>(null);
  /** Set when an autocomplete pick fires, telling MapPicker to pan there.
   *  Cleared after the pan via setMapTarget(null) so a subsequent map drag
   *  doesn't keep snapping back. Uses a fresh ref each pick (lat+lng+epoch)
   *  so React detects identical-coord re-picks too. */
  const [mapTarget, setMapTarget] = useState<{ lat: number; lng: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const onAutocompletePlace = (p: GeoPlace) => {
    setStaged({ lat: p.latitude, lng: p.longitude, label: p.formatted_address });
    setMapTarget({ lat: p.latitude, lng: p.longitude });
    setError(null);
  };

  const onMapPlace = (p: GeoPlace) => {
    setStaged({ lat: p.latitude, lng: p.longitude, label: p.formatted_address });
    setError(null);
  };

  const onSavedAddress = (a: CustomerAddress) => {
    if (a.address.latitude == null || a.address.longitude == null) return;
    setStaged({
      lat: a.address.latitude,
      lng: a.address.longitude,
      label: truncateLabel(formatAddress(a.address), 40),
    });
    setError(null);
  };

  const confirm = () => {
    if (!staged) return;
    setLocation({
      lat: staged.lat,
      lng: staged.lng,
      label: truncateLabel(staged.label),
    });
    onClose();
  };

  return (
    <Modal
      title="Set delivery location"
      onClose={onClose}
      size="wide"
      footer={
        <button
          type="button"
          className={styles.confirm}
          onClick={confirm}
          disabled={!staged}
        >
          Confirm location
        </button>
      }
    >
      <div className={styles.body}>
        {savedRows.length > 0 && (
          <div className={styles.savedSection}>
            <p className={styles.savedHeading}>Saved addresses</p>
            <ul className={styles.savedList}>
              {savedRows.map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    className={styles.savedRow}
                    onClick={() => onSavedAddress(a)}
                  >
                    <span className={styles.savedTitle}>
                      {a.label ?? "Address"}
                      {a.is_default && (
                        <span className={styles.defaultPill}>Default</span>
                      )}
                    </span>
                    <span className={styles.savedBody}>
                      {formatAddress(a.address)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <AddressAutocomplete onPlace={onAutocompletePlace} />
        <p className={styles.or}>
          {savedRows.length > 0 ? "or pick a new location" : "or pin on map"}
        </p>
        <MapPicker
          initialLat={staged?.lat}
          initialLng={staged?.lng}
          target={mapTarget}
          onPlace={onMapPlace}
          onError={setError}
        />
        {error && <span className={styles.error}>{error}</span>}
      </div>
    </Modal>
  );
}
