"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import {
  APIProvider,
  AdvancedMarker,
  Map,
} from "@vis.gl/react-google-maps";

import Modal from "@/components/Modal";
import { AddressAutocomplete } from "@/components/AddressAutocomplete";
import {
  truncateLabel,
  type GeoPlace,
} from "@/lib/geo";
import { useDeliveryLocation } from "@/lib/DeliveryLocationContext";
import { useCustomerAddresses } from "@/lib/CustomerAddressesContext";
import { useAuth } from "@/lib/AuthContext";
import { formatAddress } from "@/lib/format-address";
import { useRouter } from "@/i18n/navigation";
import type { CustomerAddress } from "@/types";

import styles from "./DeliveryLocationPicker.module.css";

interface Props {
  open: boolean;
  onClose: () => void;
}

/** Non-interactive map shown at the bottom of the picker. Pan + zoom only —
 *  never used to commit a location. Re-centers when the chip's lat/lng
 *  changes via the `key` reset (cheap remount, runs only on chip change). */
function VisualMap({ lat, lng }: { lat: number; lng: number }) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY ?? "";
  if (!apiKey) {
    return <div className={styles.mapFallback}>Map unavailable</div>;
  }
  return (
    <APIProvider apiKey={apiKey}>
      <div
        className={styles.visualMapBox}
        aria-hidden="true"
        tabIndex={-1}
      >
        <Map
          key={`${lat},${lng}`}
          defaultCenter={{ lat, lng }}
          defaultZoom={15}
          mapId="kb-visual-map"
          gestureHandling="cooperative"
          disableDefaultUI={true}
          clickableIcons={false}
          style={{ width: "100%", height: "100%" }}
        >
          <AdvancedMarker position={{ lat, lng }} />
        </Map>
      </div>
    </APIProvider>
  );
}

export function DeliveryLocationPicker({ open, onClose }: Props) {
  const { location, setLocation } = useDeliveryLocation();
  const auth = useAuth();
  const { addresses } = useCustomerAddresses();
  const router = useRouter();

  if (!open) return null;

  const isCustomer = !auth.loading && auth.dbUser?.role === "customer";

  const savedRows: CustomerAddress[] = isCustomer
    ? addresses.filter(
        (a) => a.address.latitude != null && a.address.longitude != null,
      )
    : [];

  const onSavedAddress = (a: CustomerAddress) => {
    if (a.address.latitude == null || a.address.longitude == null) return;
    setLocation({
      lat: a.address.latitude,
      lng: a.address.longitude,
      label: truncateLabel(formatAddress(a.address), 40),
    });
    onClose();
  };

  const onAutocompletePick = (p: GeoPlace) => {
    setLocation({
      lat: p.latitude,
      lng: p.longitude,
      label: truncateLabel(p.formatted_address),
    });
    onClose();
  };

  const onAddAddress = () => {
    const target = isCustomer
      ? "/account/addresses"
      : "/login?next=/account/addresses";
    router.push(target);
    onClose();
  };

  return (
    <Modal
      title="Set delivery location"
      onClose={onClose}
      size="wide"
    >
      <div className={styles.body}>
        <button
          type="button"
          className={styles.addAddressBtn}
          onClick={onAddAddress}
          disabled={auth.loading}
        >
          + Add address
        </button>
        {auth.loading ? (
          <div className={styles.skeleton} aria-busy="true" aria-live="polite">
            <div className={styles.skeletonRow} />
            <div className={styles.skeletonRow} />
            <div className={styles.skeletonRow} />
          </div>
        ) : isCustomer ? (
          <>
            {savedRows.length > 0 ? (
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
            ) : (
              <p className={styles.emptyState}>
                No saved addresses yet — use Add address above to get started.
              </p>
            )}
          </>
        ) : (
          <AddressAutocomplete onPlace={onAutocompletePick} />
        )}
        {!auth.loading && (
          <VisualMap lat={location.lat} lng={location.lng} />
        )}
      </div>
    </Modal>
  );
}
