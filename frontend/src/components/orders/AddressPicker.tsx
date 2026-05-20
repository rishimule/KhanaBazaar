"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { checkServiceability } from "@/lib/geo";
import { apiErrorKey } from "@/lib/errors";
import Modal from "@/components/Modal";
import {
  AddressFields,
  emptyAddress,
  type AddressFieldsErrors,
} from "@/components/AddressFields";
import type { Address, CustomerAddress, CustomerProfile } from "@/types";
import styles from "./AddressPicker.module.css";

export interface PickerState {
  selectedId: number | null;
  latitude: number | null;
  longitude: number | null;
  /** True when storeId is undefined OR the picked address is in-radius. */
  serviceable: boolean;
  /** True while profile is loading OR any serviceability check unresolved. */
  loading: boolean;
}

interface Props {
  value: number | null;
  onChange: (id: number) => void;
  /** When set, each saved address is checked against this store's delivery
   *  radius via /api/v1/geo/serviceability and disabled if outside. */
  storeId?: number;
  /** Fires whenever the picker's effective state changes. Always called
   *  (never null) so parents can gate on `loading` even before a selection
   *  exists (e.g. zero-serviceable). */
  onStateChange?: (state: PickerState) => void;
}

export default function AddressPicker({
  value, onChange, storeId, onStateChange,
}: Props) {
  const t = useTranslations("Address");
  const tAcc = useTranslations("Account.addresses");
  const tErr = useTranslations("Errors");
  const { token } = useAuth();
  const [addresses, setAddresses] = useState<CustomerAddress[]>([]);
  const [profileLoading, setProfileLoading] = useState(true);
  /** id → serviceable? Missing entry means "still checking" or "no lat/lng". */
  const [serviceability, setServiceability] = useState<Record<number, boolean>>({});
  const didAutoSelect = useRef(false);

  const [addModalOpen, setAddModalOpen] = useState(false);
  const [addForm, setAddForm] = useState<{
    label: string;
    is_default: boolean;
    address: Address;
  }>({ label: "", is_default: false, address: emptyAddress() });
  const [addErrors, setAddErrors] = useState<AddressFieldsErrors>({});
  const [modalError, setModalError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [geolocating, setGeolocating] = useState(false);

  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const listboxRef = useRef<HTMLUListElement | null>(null);
  const optionRefs = useRef<Map<number, HTMLLIElement>>(new Map());

  useEffect(() => {
    if (!token) return;
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then((data) => { setAddresses(data.addresses); })
      .finally(() => setProfileLoading(false));
  }, [token]);

  useEffect(() => {
    if (storeId === undefined || addresses.length === 0) return;
    let cancelled = false;

    const checks = addresses.map(async (a) => {
      if (a.address.latitude == null || a.address.longitude == null) {
        return [a.id, false] as const;
      }
      try {
        const r = await checkServiceability(
          a.address.latitude, a.address.longitude, storeId,
        );
        return [a.id, r.serviceable] as const;
      } catch {
        return [a.id, false] as const;
      }
    });

    Promise.all(checks).then((entries) => {
      if (cancelled) return;
      setServiceability(Object.fromEntries(entries));
    });

    return () => { cancelled = true; };
  }, [addresses, storeId]);

  const allSettled =
    !profileLoading &&
    (storeId === undefined || addresses.every((a) => a.id in serviceability));

  useEffect(() => {
    if (!allSettled) return;
    if (didAutoSelect.current) return;
    if (value !== null) { didAutoSelect.current = true; return; }
    if (addresses.length === 0) { didAutoSelect.current = true; return; }

    const isOk = (id: number) =>
      storeId === undefined || serviceability[id] === true;

    const def = addresses.find((a) => a.is_default);
    const pick =
      (def && isOk(def.id) ? def : null) ??
      addresses.find((a) => isOk(a.id)) ??
      null;

    if (pick) onChange(pick.id);
    didAutoSelect.current = true;
  }, [allSettled, addresses, serviceability, storeId, value, onChange]);

  useEffect(() => {
    if (!onStateChange) return;
    const picked = value != null ? addresses.find((a) => a.id === value) : undefined;
    onStateChange({
      selectedId: picked?.id ?? null,
      latitude: picked?.address.latitude ?? null,
      longitude: picked?.address.longitude ?? null,
      serviceable:
        picked === undefined
          ? false
          : storeId === undefined
            ? true
            : serviceability[picked.id] === true,
      loading: !allSettled,
    });
  }, [value, addresses, serviceability, storeId, allSettled, onStateChange]);

  const openAddModal = () => {
    setAddForm({ label: "", is_default: false, address: emptyAddress() });
    setAddErrors({});
    setModalError(null);
    setAddModalOpen(true);
  };

  const closeAddModal = () => {
    if (saving) return;
    setAddModalOpen(false);
  };

  const useCurrentLocation = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setModalError(tAcc("geolocationUnavailable"));
      return;
    }
    setModalError(null);
    setGeolocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude } = pos.coords;
        try {
          const place = await get<{
            address_line1?: string;
            city?: string;
            state?: string;
            pincode?: string;
            country?: string;
            latitude: number;
            longitude: number;
          }>(`/api/v1/geo/reverse?lat=${latitude}&lng=${longitude}`, token);
          setAddForm((curr) => ({
            ...curr,
            address: {
              ...curr.address,
              address_line1: place.address_line1 ?? curr.address.address_line1,
              city: place.city ?? curr.address.city,
              state: place.state ?? curr.address.state,
              pincode: place.pincode ?? curr.address.pincode,
              country: place.country ?? curr.address.country,
              latitude,
              longitude,
              location_source: "geocoded",
            },
          }));
        } catch {
          setModalError(tAcc("geolocationGeocodeError"));
          setAddForm((curr) => ({
            ...curr,
            address: {
              ...curr.address,
              latitude,
              longitude,
              location_source: "geocoded",
            },
          }));
        } finally {
          setGeolocating(false);
        }
      },
      (err) => {
        setGeolocating(false);
        setModalError(
          err.code === err.PERMISSION_DENIED
            ? tAcc("geolocationDenied")
            : tAcc("geolocationError"),
        );
      },
    );
  };

  const validationErrorsForPrefix = (
    error: unknown,
    prefix: string,
  ): AddressFieldsErrors => {
    const detail = (error as { detail?: unknown })?.detail;
    if (!Array.isArray(detail)) return {};
    const result: AddressFieldsErrors = {};
    for (const issue of detail) {
      const loc = (issue as { loc?: Array<string | number> }).loc;
      const msg = (issue as { msg?: string }).msg;
      if (!Array.isArray(loc) || typeof msg !== "string") continue;
      const i = loc.indexOf(prefix);
      if (i === -1) continue;
      const field = loc[i + 1];
      if (typeof field === "string") {
        (result as Record<string, string>)[field] = msg;
      }
    }
    return result;
  };

  const onSaveAddress = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || saving) return;
    setSaving(true);
    setAddErrors({});
    setModalError(null);
    const prevIds = new Set(addresses.map((a) => a.id));
    const payload = {
      label: addForm.label.trim().length > 0 ? addForm.label.trim() : null,
      is_default: addForm.is_default,
      address: addForm.address,
    };
    try {
      const next = await post<CustomerProfile>(
        "/api/v1/customers/me/addresses",
        payload,
        token,
      );
      const newId = next.addresses.find((a) => !prevIds.has(a.id))?.id ?? null;
      setAddresses(next.addresses);
      setAddModalOpen(false);
      if (newId != null) {
        onChange(newId);
      }
    } catch (error) {
      setAddErrors(validationErrorsForPrefix(error, "address"));
      const key = apiErrorKey(error);
      if (key) {
        setModalError(tErr(key.replace(/^Errors\./, "")));
      } else {
        const detail = (error as { detail?: unknown })?.detail;
        if (typeof detail === "string") {
          setModalError(detail);
        } else {
          setModalError(tAcc("saveAddressError"));
        }
      }
    } finally {
      setSaving(false);
    }
  };

  const renderAddModal = () => (
    <Modal title={tAcc("addAddressFormTitle")} onClose={closeAddModal} size="wide">
      <form className={styles.modalBody} onSubmit={onSaveAddress}>
        {modalError && <div className={styles.modalError}>{modalError}</div>}

        <div className={styles.modalField}>
          <label className={styles.label} htmlFor="add-address-label">
            {tAcc("labelLabel")}
          </label>
          <input
            id="add-address-label"
            className={styles.modalInput}
            value={addForm.label}
            onChange={(e) =>
              setAddForm((curr) => ({ ...curr, label: e.target.value }))
            }
            placeholder={tAcc("labelPlaceholder")}
            maxLength={60}
            disabled={saving}
          />
        </div>

        <button
          type="button"
          className={styles.addBtn}
          onClick={useCurrentLocation}
          disabled={saving || geolocating}
        >
          {geolocating ? tAcc("geolocating") : tAcc("useCurrentLocation")}
        </button>

        <AddressFields
          value={addForm.address}
          onChange={(address) =>
            setAddForm((curr) => ({ ...curr, address }))
          }
          errors={addErrors}
          disabled={saving}
        />

        <label className={styles.modalCheckboxRow}>
          <input
            type="checkbox"
            checked={addForm.is_default}
            onChange={(e) =>
              setAddForm((curr) => ({ ...curr, is_default: e.target.checked }))
            }
            disabled={saving}
          />
          {tAcc("makeDefault")}
        </label>

        <div className={styles.modalActions}>
          <button
            type="button"
            className="btn btn-outline"
            onClick={closeAddModal}
            disabled={saving}
          >
            {tAcc("cancel")}
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={saving}
          >
            {saving ? tAcc("saving") : tAcc("saveAddress")}
          </button>
        </div>
      </form>
    </Modal>
  );

  const { deliverableOptions, outsideOptions, visibleOptions } = useMemo(() => {
    const def = addresses.find((a) => a.is_default);

    const deliverable = !allSettled || storeId === undefined
      ? [...addresses]
      : addresses.filter((a) => serviceability[a.id] === true);
    const outside = !allSettled || storeId === undefined
      ? []
      : addresses.filter((a) => serviceability[a.id] === false);

    const deliverableOrdered = def && deliverable.includes(def)
      ? [def, ...deliverable.filter((a) => a.id !== def.id)]
      : deliverable;

    const flat: { id: number; selectable: boolean }[] = [
      ...deliverableOrdered.map((a) => ({ id: a.id, selectable: true })),
      ...outside.map((a) => ({ id: a.id, selectable: false })),
    ];
    return {
      deliverableOptions: deliverableOrdered,
      outsideOptions: outside,
      visibleOptions: flat,
    };
  }, [addresses, serviceability, storeId, allSettled]);

  const selectedAddress = useMemo(
    () => addresses.find((a) => a.id === value) ?? null,
    [addresses, value],
  );

  const indexById = useCallback(
    (id: number | null) => {
      if (id == null) return -1;
      return visibleOptions.findIndex((o) => o.id === id);
    },
    [visibleOptions],
  );

  const firstSelectableIndex = useCallback(() => {
    return visibleOptions.findIndex((o) => o.selectable);
  }, [visibleOptions]);

  const moveActive = useCallback(
    (dir: 1 | -1) => {
      if (visibleOptions.length === 0) return;
      let i = activeIndex;
      for (let step = 0; step < visibleOptions.length; step += 1) {
        i = (i + dir + visibleOptions.length) % visibleOptions.length;
        if (visibleOptions[i].selectable) {
          setActiveIndex(i);
          return;
        }
      }
    },
    [activeIndex, visibleOptions],
  );

  const moveToFirst = useCallback(() => {
    const i = firstSelectableIndex();
    if (i >= 0) setActiveIndex(i);
  }, [firstSelectableIndex]);

  const moveToLast = useCallback(() => {
    for (let i = visibleOptions.length - 1; i >= 0; i -= 1) {
      if (visibleOptions[i].selectable) {
        setActiveIndex(i);
        return;
      }
    }
  }, [visibleOptions]);

  const closeListbox = useCallback(() => {
    setIsOpen(false);
    triggerRef.current?.focus();
  }, []);

  const selectActive = useCallback(() => {
    const opt = visibleOptions[activeIndex];
    if (!opt || !opt.selectable) return;
    onChange(opt.id);
    setIsOpen(false);
    triggerRef.current?.focus();
  }, [activeIndex, onChange, visibleOptions]);

  const openListbox = useCallback(() => {
    const current = indexById(value);
    const startAt =
      current >= 0 && visibleOptions[current]?.selectable
        ? current
        : firstSelectableIndex();
    if (startAt >= 0) setActiveIndex(startAt);
    setIsOpen(true);
  }, [indexById, value, visibleOptions, firstSelectableIndex]);

  useEffect(() => {
    if (addModalOpen && isOpen) setIsOpen(false);
  }, [addModalOpen, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onMouseDown = (e: MouseEvent) => {
      const t = triggerRef.current;
      const lb = listboxRef.current;
      const target = e.target as Node | null;
      if (!target) return;
      if (t && t.contains(target)) return;
      if (lb && lb.contains(target)) return;
      setIsOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const opt = visibleOptions[activeIndex];
    if (!opt) return;
    const el = optionRefs.current.get(opt.id);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, isOpen, visibleOptions]);

  const onTriggerKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          if (!isOpen) {
            openListbox();
          } else {
            moveActive(1);
          }
          break;
        case "ArrowUp":
          e.preventDefault();
          if (!isOpen) {
            openListbox();
          } else {
            moveActive(-1);
          }
          break;
        case "Home":
          if (isOpen) {
            e.preventDefault();
            moveToFirst();
          }
          break;
        case "End":
          if (isOpen) {
            e.preventDefault();
            moveToLast();
          }
          break;
        case "Enter":
        case " ":
          if (isOpen) {
            e.preventDefault();
            selectActive();
          } else {
            e.preventDefault();
            openListbox();
          }
          break;
        case "Escape":
          if (isOpen) {
            e.preventDefault();
            closeListbox();
          }
          break;
        case "Tab":
          if (isOpen) setIsOpen(false);
          break;
        default:
          break;
      }
    },
    [
      isOpen,
      openListbox,
      moveActive,
      moveToFirst,
      moveToLast,
      selectActive,
      closeListbox,
    ],
  );

  if (profileLoading) return <div className={styles.loading}>{t("pickerLoading")}</div>;
  if (addresses.length === 0) {
    return (
      <>
        <div className={styles.empty}>
          {t("pickerEmpty")}
          <div className={styles.emptyActions}>
            <button
              type="button"
              className={styles.addBtn}
              onClick={openAddModal}
            >
              + {tAcc("addAddress")}
            </button>
          </div>
        </div>
        {addModalOpen && renderAddModal()}
      </>
    );
  }

  const hasAnyServiceable =
    storeId === undefined ||
    addresses.some((a) => serviceability[a.id] === true);

  if (allSettled && !hasAnyServiceable) {
    return (
      <>
        <div className={styles.empty}>
          {t("noServiceableTitle")}
          <div className={styles.emptyActions}>
            <button
              type="button"
              className={styles.addBtn}
              onClick={openAddModal}
            >
              + {tAcc("addAddress")}
            </button>
          </div>
        </div>
        {addModalOpen && renderAddModal()}
      </>
    );
  }

  const activeOptionId =
    isOpen && visibleOptions[activeIndex]
      ? `addr-opt-${visibleOptions[activeIndex].id}`
      : undefined;

  const triggerLabel = selectedAddress
    ? `${selectedAddress.label ?? t("fallbackLabel")} — ${selectedAddress.address.address_line1}, ${selectedAddress.address.city} ${selectedAddress.address.pincode}`
    : t("fallbackLabel");

  return (
    <>
      <div className={styles.picker}>
        <div className={styles.header}>
          <span id="addr-picker-label" className={styles.label}>
            {t("deliverTo")}
          </span>
          <button
            type="button"
            className={styles.addBtn}
            onClick={openAddModal}
          >
            + {tAcc("addAddress")}
          </button>
        </div>
        <button
          ref={triggerRef}
          type="button"
          className={styles.comboTrigger}
          role="combobox"
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls="addr-listbox"
          aria-labelledby="addr-picker-label"
          aria-activedescendant={activeOptionId}
          onClick={() => (isOpen ? setIsOpen(false) : openListbox())}
          onKeyDown={onTriggerKeyDown}
          onBlur={(e) => {
            const next = e.relatedTarget as Node | null;
            const lb = listboxRef.current;
            if (next && lb && lb.contains(next)) return;
            if (isOpen) setIsOpen(false);
          }}
        >
          <span
            className={`${styles.comboLabel} ${selectedAddress ? "" : styles.comboPlaceholder}`}
          >
            {triggerLabel}
          </span>
          <span className={styles.comboChevron} aria-hidden="true">▾</span>
        </button>
        {isOpen && (
          <ul
            ref={listboxRef}
            id="addr-listbox"
            role="listbox"
            tabIndex={-1}
            className={styles.listbox}
          >
            {deliverableOptions.map((a) => {
              const idx = visibleOptions.findIndex((o) => o.id === a.id);
              const selected = a.id === value;
              const isActive = idx === activeIndex;
              return (
                <li
                  key={a.id}
                  ref={(el) => {
                    if (el) optionRefs.current.set(a.id, el);
                    else optionRefs.current.delete(a.id);
                  }}
                  id={`addr-opt-${a.id}`}
                  role="option"
                  aria-selected={selected}
                  data-active={isActive ? "true" : undefined}
                  className={`${styles.option} ${selected ? styles.optionSelected : ""}`}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => {
                    onChange(a.id);
                    setIsOpen(false);
                    triggerRef.current?.focus();
                  }}
                >
                  <span className={styles.optionCheck} aria-hidden="true">
                    {selected ? "✓" : ""}
                  </span>
                  <span className={styles.optionLabel}>
                    {a.label ?? t("fallbackLabel")}
                  </span>
                  <span className={styles.optionAddress}>
                    {a.address.address_line1}, {a.address.city} {a.address.pincode}
                  </span>
                </li>
              );
            })}
            {outsideOptions.length > 0 && (
              <li
                role="presentation"
                className={styles.sectionHeader}
                aria-hidden="true"
              >
                {t("outsideDeliveryAreaHeader")}
              </li>
            )}
            {outsideOptions.map((a) => {
              const idx = visibleOptions.findIndex((o) => o.id === a.id);
              const isActive = idx === activeIndex;
              return (
                <li
                  key={a.id}
                  ref={(el) => {
                    if (el) optionRefs.current.set(a.id, el);
                    else optionRefs.current.delete(a.id);
                  }}
                  id={`addr-opt-${a.id}`}
                  role="option"
                  aria-selected={false}
                  aria-disabled="true"
                  data-active={isActive ? "true" : undefined}
                  className={styles.option}
                >
                  <span className={styles.optionCheck} aria-hidden="true" />
                  <span className={styles.optionLabel}>
                    {a.label ?? t("fallbackLabel")}
                  </span>
                  <span className={styles.optionAddress}>
                    {a.address.address_line1}, {a.address.city} {a.address.pincode}
                  </span>
                  <span className={styles.optionBadge}>
                    {t("outsideAreaBadge")}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {addModalOpen && renderAddModal()}
    </>
  );
}
