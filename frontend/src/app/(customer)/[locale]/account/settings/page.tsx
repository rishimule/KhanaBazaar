"use client";

import { useEffect, useMemo, useState } from "react";
import { AddressFields, emptyAddress } from "@/components/AddressFields";
import { del, get, patch, post, put } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { formatAddress } from "@/lib/format-address";
import type { AddressFieldsErrors } from "@/components/AddressFields";
import type { Address, CustomerAddress, CustomerProfile } from "@/types";
import styles from "./page.module.css";

interface ProfileForm {
  first_name: string;
  last_name: string;
  phone: string;
}

interface ProfileErrors {
  first_name?: string;
  last_name?: string;
  phone?: string;
}

interface AddressForm {
  id: number | null;
  label: string;
  is_default: boolean;
  address: Address;
}

interface FastApiValidationIssue {
  loc?: Array<string | number>;
  msg?: string;
}

const PHONE_RE = /^[0-9+() -]{7,20}$/;

function profileFormFrom(profile: CustomerProfile): ProfileForm {
  return {
    first_name: profile.first_name,
    last_name: profile.last_name ?? "",
    phone: profile.phone ?? "",
  };
}

function blankAddressForm(): AddressForm {
  return {
    id: null,
    label: "",
    is_default: false,
    address: emptyAddress(),
  };
}

function addressFormFrom(customerAddress: CustomerAddress): AddressForm {
  return {
    id: customerAddress.id,
    label: customerAddress.label ?? "",
    is_default: customerAddress.is_default,
    address: customerAddress.address,
  };
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as FastApiValidationIssue;
    if (typeof first.msg === "string") return first.msg;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

function validationErrorsForPrefix(
  error: unknown,
  prefix: string
): Record<string, string> {
  const detail = (error as { detail?: unknown })?.detail;
  if (!Array.isArray(detail)) return {};

  return detail.reduce<Record<string, string>>(
    (acc, issue: FastApiValidationIssue) => {
      if (!Array.isArray(issue.loc) || typeof issue.msg !== "string") return acc;
      const prefixIndex = issue.loc.indexOf(prefix);
      if (prefixIndex === -1) return acc;
      const field = issue.loc[prefixIndex + 1];
      if (typeof field === "string") acc[field] = issue.msg;
      return acc;
    },
    {}
  );
}

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export default function AccountSettingsPage() {
  const { token } = useAuth();
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [profileForm, setProfileForm] = useState<ProfileForm>({
    first_name: "",
    last_name: "",
    phone: "",
  });
  const [profileErrors, setProfileErrors] = useState<ProfileErrors>({});
  const [addressForm, setAddressForm] = useState<AddressForm | null>(null);
  const [addressErrors, setAddressErrors] = useState<AddressFieldsErrors>({});
  const [sectionError, setSectionError] = useState<string | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingAddress, setSavingAddress] = useState(false);
  const [busyAddressId, setBusyAddressId] = useState<number | null>(null);

  useEffect(() => {
    if (!token) {
      setLoadingProfile(false);
      setSectionError("Could not load account settings.");
      return;
    }

    let active = true;
    setLoadingProfile(true);
    get<CustomerProfile>("/api/v1/customers/me", token)
      .then((data) => {
        if (!active) return;
        setProfile(data);
        setProfileForm(profileFormFrom(data));
      })
      .catch((error) => {
        if (!active) return;
        setSectionError(apiErrorMessage(error, "Could not load account settings."));
      })
      .finally(() => {
        if (active) setLoadingProfile(false);
      });

    return () => {
      active = false;
    };
  }, [token]);

  const sortedAddresses = useMemo(() => {
    if (!profile) return [];
    return [...profile.addresses].sort((a, b) => {
      if (a.is_default === b.is_default) return a.id - b.id;
      return a.is_default ? -1 : 1;
    });
  }, [profile]);

  const validateProfile = (): ProfileErrors => {
    const errors: ProfileErrors = {};
    if (!profileForm.first_name.trim()) {
      errors.first_name = "First name is required.";
    }
    if (profileForm.phone.trim() && !PHONE_RE.test(profileForm.phone.trim())) {
      errors.phone = "Use 7-20 digits, spaces, +, -, or parentheses.";
    }
    return errors;
  };

  const saveProfile = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    setSectionError(null);
    const errors = validateProfile();
    setProfileErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSavingProfile(true);
    try {
      const next = await patch<CustomerProfile>(
        "/api/v1/customers/me",
        {
          first_name: profileForm.first_name.trim(),
          last_name: normalizeOptional(profileForm.last_name),
          phone: normalizeOptional(profileForm.phone),
        },
        token
      );
      setProfile(next);
      setProfileForm(profileFormFrom(next));
      setProfileErrors({});
    } catch (error) {
      setProfileErrors(validationErrorsForPrefix(error, "body") as ProfileErrors);
      setSectionError(apiErrorMessage(error, "Could not save profile changes."));
    } finally {
      setSavingProfile(false);
    }
  };

  const openNewAddressForm = () => {
    setAddressErrors({});
    setSectionError(null);
    setAddressForm(blankAddressForm());
  };

  const editAddress = (customerAddress: CustomerAddress) => {
    setAddressErrors({});
    setSectionError(null);
    setAddressForm(addressFormFrom(customerAddress));
  };

  const saveAddress = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token || !addressForm) return;
    setSectionError(null);
    setAddressErrors({});
    setSavingAddress(true);

    const payload = {
      label: normalizeOptional(addressForm.label),
      is_default: addressForm.is_default,
      address: addressForm.address,
    };

    try {
      const next =
        addressForm.id === null
          ? await post<CustomerProfile>("/api/v1/customers/me/addresses", payload, token)
          : await put<CustomerProfile>(
              `/api/v1/customers/me/addresses/${addressForm.id}`,
              payload,
              token
            );
      setProfile(next);
      setAddressForm(null);
      setAddressErrors({});
    } catch (error) {
      setAddressErrors(
        validationErrorsForPrefix(error, "address") as AddressFieldsErrors
      );
      setSectionError(apiErrorMessage(error, "Could not save delivery address."));
    } finally {
      setSavingAddress(false);
    }
  };

  const setDefaultAddress = async (customerAddress: CustomerAddress) => {
    if (!token || customerAddress.is_default) return;
    setSectionError(null);
    setBusyAddressId(customerAddress.id);
    try {
      const next = await post<CustomerProfile>(
        `/api/v1/customers/me/addresses/${customerAddress.id}/default`,
        undefined,
        token
      );
      setProfile(next);
    } catch (error) {
      setSectionError(apiErrorMessage(error, "Could not set default address."));
    } finally {
      setBusyAddressId(null);
    }
  };

  const deleteAddress = async (customerAddress: CustomerAddress) => {
    if (!token) return;
    const label = customerAddress.label || "this address";
    if (!window.confirm(`Delete ${label}?`)) return;

    setSectionError(null);
    setBusyAddressId(customerAddress.id);
    try {
      const next = await del<CustomerProfile>(
        `/api/v1/customers/me/addresses/${customerAddress.id}`,
        token
      );
      setProfile(next);
      if (addressForm?.id === customerAddress.id) setAddressForm(null);
    } catch (error) {
      setSectionError(apiErrorMessage(error, "Could not delete address."));
    } finally {
      setBusyAddressId(null);
    }
  };

  if (loadingProfile) {
    return <div className={styles.loading}>Loading account settings…</div>;
  }

  if (!profile) {
    return (
      <div className={styles.panel}>
        <div className={styles.errorBanner}>
          {sectionError ?? "Could not load account settings."}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {sectionError && <div className={styles.errorBanner}>{sectionError}</div>}

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Profile</h2>
            <p className={styles.sectionSubtitle}>{profile.email}</p>
          </div>
        </div>

        <form className={styles.profileForm} onSubmit={saveProfile}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="first-name">
              First name
            </label>
            <input
              id="first-name"
              className={`${styles.input} ${
                profileErrors.first_name ? styles.inputError : ""
              }`}
              value={profileForm.first_name}
              onChange={(event) =>
                setProfileForm((current) => ({
                  ...current,
                  first_name: event.target.value,
                }))
              }
              maxLength={80}
              required
            />
            {profileErrors.first_name && (
              <span className={styles.errorText}>{profileErrors.first_name}</span>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="last-name">
              Last name
            </label>
            <input
              id="last-name"
              className={`${styles.input} ${
                profileErrors.last_name ? styles.inputError : ""
              }`}
              value={profileForm.last_name}
              onChange={(event) =>
                setProfileForm((current) => ({
                  ...current,
                  last_name: event.target.value,
                }))
              }
              maxLength={80}
            />
            {profileErrors.last_name && (
              <span className={styles.errorText}>{profileErrors.last_name}</span>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="phone">
              Phone
            </label>
            <input
              id="phone"
              className={`${styles.input} ${
                profileErrors.phone ? styles.inputError : ""
              }`}
              value={profileForm.phone}
              onChange={(event) =>
                setProfileForm((current) => ({
                  ...current,
                  phone: event.target.value,
                }))
              }
              inputMode="tel"
              maxLength={20}
            />
            {profileErrors.phone && (
              <span className={styles.errorText}>{profileErrors.phone}</span>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="email">
              Email
            </label>
            <input
              id="email"
              className={styles.input}
              value={profile.email}
              readOnly
              disabled
            />
          </div>

          <div className={styles.formActions}>
            <button className="btn btn-primary" type="submit" disabled={savingProfile}>
              {savingProfile ? "Saving…" : "Save profile"}
            </button>
          </div>
        </form>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Saved delivery addresses</h2>
            <p className={styles.sectionSubtitle}>
              {sortedAddresses.length} saved address
              {sortedAddresses.length === 1 ? "" : "es"}
            </p>
          </div>
          <button className="btn btn-outline" type="button" onClick={openNewAddressForm}>
            Add address
          </button>
        </div>

        {sortedAddresses.length === 0 && (
          <div className={styles.emptyState}>
            <p>No delivery addresses are saved.</p>
            <button className="btn btn-primary" type="button" onClick={openNewAddressForm}>
              Add address
            </button>
          </div>
        )}

        {sortedAddresses.length > 0 && (
          <div className={styles.addressGrid}>
            {sortedAddresses.map((customerAddress) => (
              <article className={styles.addressCard} key={customerAddress.id}>
                <div className={styles.addressCardHeader}>
                  <div>
                    <h3 className={styles.addressLabel}>
                      {customerAddress.label || "Address"}
                    </h3>
                    {customerAddress.is_default && (
                      <span className={styles.defaultBadge}>Default</span>
                    )}
                  </div>
                </div>
                <p className={styles.addressText}>
                  {formatAddress(customerAddress.address)}
                </p>
                <div className={styles.addressActions}>
                  <button
                    className={styles.textButton}
                    type="button"
                    onClick={() => editAddress(customerAddress)}
                    disabled={busyAddressId === customerAddress.id}
                  >
                    Edit
                  </button>
                  <button
                    className={styles.textButton}
                    type="button"
                    onClick={() => setDefaultAddress(customerAddress)}
                    disabled={
                      customerAddress.is_default ||
                      busyAddressId === customerAddress.id
                    }
                  >
                    Set default
                  </button>
                  <button
                    className={`${styles.textButton} ${styles.dangerButton}`}
                    type="button"
                    onClick={() => deleteAddress(customerAddress)}
                    disabled={busyAddressId === customerAddress.id}
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}

        {addressForm && (
          <form className={styles.addressForm} onSubmit={saveAddress}>
            <div className={styles.addressFormHeader}>
              <h3 className={styles.addressFormTitle}>
                {addressForm.id === null
                  ? "Add delivery address"
                  : "Edit delivery address"}
              </h3>
              <button
                className={styles.textButton}
                type="button"
                onClick={() => setAddressForm(null)}
                disabled={savingAddress}
              >
                Cancel
              </button>
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="address-label">
                Label
              </label>
              <input
                id="address-label"
                className={styles.input}
                value={addressForm.label}
                onChange={(event) =>
                  setAddressForm((current) =>
                    current ? { ...current, label: event.target.value } : current
                  )
                }
                placeholder="Home, Work, Family"
                maxLength={60}
                disabled={savingAddress}
              />
            </div>

            <AddressFields
              value={addressForm.address}
              onChange={(address) =>
                setAddressForm((current) =>
                  current ? { ...current, address } : current
                )
              }
              errors={addressErrors}
              disabled={savingAddress}
            />

            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={addressForm.is_default}
                onChange={(event) =>
                  setAddressForm((current) =>
                    current
                      ? { ...current, is_default: event.target.checked }
                      : current
                  )
                }
                disabled={savingAddress}
              />
              Make this the default delivery address
            </label>

            <div className={styles.formActions}>
              <button className="btn btn-primary" type="submit" disabled={savingAddress}>
                {savingAddress ? "Saving…" : "Save address"}
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
