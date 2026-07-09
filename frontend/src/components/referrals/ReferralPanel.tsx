"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { getIndianStates } from "@/lib/indian-states";
import {
  listMyReferrals,
  submitReferral,
  type Referral,
  type ReferralStatus,
  type ReferralTargetRole,
} from "@/lib/referrals";
import styles from "./ReferralPanel.module.css";

const STATUS_CLASS: Record<ReferralStatus, string> = {
  pending_review: styles.chipPending,
  approved: styles.chipApproved,
  active: styles.chipActive,
  rejected: styles.chipRejected,
  expired: styles.chipExpired,
};

/** Shared "Referrals" panel rendered on both the customer and seller
 * dashboards: an "Onboard New" form + a "My Referrals" status list. */
export default function ReferralPanel() {
  const t = useTranslations("Referrals");
  const { token } = useAuth();

  const [targetRole, setTargetRole] = useState<ReferralTargetRole>("customer");
  const [name, setName] = useState("");
  const [state, setState] = useState("");
  const [area, setArea] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");

  const [states, setStates] = useState<string[]>([]);
  const [list, setList] = useState<Referral[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    getIndianStates()
      .then(setStates)
      .catch(() => setStates([]));
  }, []);

  useEffect(() => {
    if (!token) return;
    setListLoading(true);
    listMyReferrals(token)
      .then((res) => setList(res.items))
      .catch(() => setList([]))
      .finally(() => setListLoading(false));
  }, [token]);

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!token) return;
    if (!email.trim() && !phone.trim()) {
      setError(t("errContactRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(false);
    try {
      const created = await submitReferral(token, {
        target_role: targetRole,
        invitee_name: name.trim(),
        invitee_email: email.trim() || undefined,
        invitee_phone: phone.trim() || undefined,
        location_state: state,
        location_area: area.trim(),
      });
      setList((prev) => [created, ...prev]);
      setSuccess(true);
      setName("");
      setArea("");
      setEmail("");
      setPhone("");
    } catch (err) {
      if (err instanceof ApiError) {
        const code = (err.detail as unknown as { error?: string })?.error;
        if (code === "already_invited") setError(t("errAlreadyInvited"));
        else if (code === "already_registered") setError(t("errAlreadyRegistered"));
        else setError(t("errorGeneric"));
      } else {
        setError(t("errorGeneric"));
      }
    } finally {
      setBusy(false);
    }
  };

  const contactOf = (r: Referral) => r.invitee_email || r.invitee_phone || "—";
  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });

  return (
    <div className={styles.panel}>
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>{t("onboardTitle")}</h2>
        <p className={styles.cardSubtitle}>{t("onboardSubtitle")}</p>

        <form className={styles.form} onSubmit={submit}>
          <div className={styles.field}>
            <span className={styles.label}>{t("roleLabel")}</span>
            <div className={styles.segmented} role="radiogroup" aria-label={t("roleLabel")}>
              <button
                type="button"
                role="radio"
                aria-checked={targetRole === "customer"}
                className={targetRole === "customer" ? styles.segActive : styles.seg}
                onClick={() => setTargetRole("customer")}
              >
                {t("roleCustomer")}
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={targetRole === "seller"}
                className={targetRole === "seller" ? styles.segActive : styles.seg}
                onClick={() => setTargetRole("seller")}
              >
                {t("roleSeller")}
              </button>
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="ref-name">{t("nameLabel")}</label>
            <input
              id="ref-name"
              className={styles.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("namePlaceholder")}
              required
              maxLength={120}
            />
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ref-state">{t("stateLabel")}</label>
              <select
                id="ref-state"
                className={styles.input}
                value={state}
                onChange={(e) => setState(e.target.value)}
                required
              >
                <option value="" disabled>{t("statePlaceholder")}</option>
                {states.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ref-area">{t("areaLabel")}</label>
              <input
                id="ref-area"
                className={styles.input}
                value={area}
                onChange={(e) => setArea(e.target.value)}
                placeholder={t("areaPlaceholder")}
                required
                maxLength={160}
              />
            </div>
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ref-email">{t("emailLabel")}</label>
              <input
                id="ref-email"
                type="email"
                className={styles.input}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("emailPlaceholder")}
                maxLength={254}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="ref-phone">{t("phoneLabel")}</label>
              <input
                id="ref-phone"
                className={styles.input}
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder={t("phonePlaceholder")}
                maxLength={20}
              />
            </div>
          </div>
          <p className={styles.help}>{t("contactHelp")}</p>

          <div className={styles.actions}>
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy ? t("submitting") : t("submit")}
            </button>
            {success && <span className={styles.toast}>{t("successMsg")}</span>}
          </div>
          {error && (
            <div className={styles.errorText} role="alert">{error}</div>
          )}
        </form>
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>{t("listTitle")}</h2>
        {listLoading ? (
          <p className={styles.muted}>{t("loading")}</p>
        ) : list.length === 0 ? (
          <p className={styles.muted}>{t("empty")}</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t("colInvitee")}</th>
                  <th>{t("colContact")}</th>
                  <th>{t("colRole")}</th>
                  <th>{t("colStatus")}</th>
                  <th>{t("colDate")}</th>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id}>
                    <td>{r.invitee_name}</td>
                    <td className={styles.muted}>{contactOf(r)}</td>
                    <td>{t(`role.${r.target_role}`)}</td>
                    <td>
                      <span className={`${styles.chip} ${STATUS_CLASS[r.status]}`}>
                        {t(`status.${r.status}`)}
                      </span>
                    </td>
                    <td className={styles.muted}>{fmtDate(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
