"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import DataTable, { type Column } from "@/components/DataTable";
import { useAuth } from "@/lib/AuthContext";
import {
  adminCampaignAudienceCount,
  adminCreateCampaign,
  adminListCampaigns,
  adminSendCampaign,
  uploadCampaignImage,
} from "@/lib/campaigns";
import type {
  Campaign,
  CampaignAudienceCount,
  CampaignChannel,
  CampaignCreateInput,
  NotificationAudience,
} from "@/types";
import styles from "./page.module.css";

const FEE_MODELS = ["freebie", "subscription", "order_value_percent", "pay_per_transaction"];

export default function AdminNotificationsPage() {
  const t = useTranslations("Admin.notifications");
  const { token } = useAuth();

  const [audience, setAudience] = useState<NotificationAudience>("both");
  const [stateName, setStateName] = useState("");
  const [city, setCity] = useState("");
  const [newOnboarded, setNewOnboarded] = useState(false);
  const [feeModels, setFeeModels] = useState<string[]>([]);
  const [expiringSoon, setExpiringSoon] = useState(false);
  const [email, setEmail] = useState(false);
  const [sms, setSms] = useState(false);
  const [isEssential, setIsEssential] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [ctaUrl, setCtaUrl] = useState("");
  const [ctaLabel, setCtaLabel] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);

  const [preparedId, setPreparedId] = useState<number | null>(null);
  const [preview, setPreview] = useState<CampaignAudienceCount | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  // Any field edit invalidates a prepared draft so the next action re-creates it.
  const bump = () => {
    setPreparedId(null);
    setPreview(null);
  };

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      setCampaigns(await adminListCampaigns(token));
    } catch {
      /* non-fatal */
    }
  }, [token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function buildInput(): CampaignCreateInput {
    const filters: CampaignCreateInput["filters"] = {};
    if (audience !== "both") {
      if (stateName.trim()) filters.state = stateName.trim();
      if (city.trim()) filters.cities = [city.trim()];
      if (newOnboarded) filters.new_onboarded = true;
      if (audience === "sellers") {
        if (feeModels.length) filters.seller_fee_models = feeModels;
        if (expiringSoon) filters.seller_expiring_soon = true;
      }
    }
    const channels: CampaignChannel[] = ["in_app"];
    if (email) channels.push("email");
    if (sms) channels.push("sms");
    return {
      audience,
      filters,
      channels,
      title: title.trim(),
      body: body.trim(),
      cta_url: ctaUrl.trim() || null,
      cta_label: ctaLabel.trim() || null,
      is_essential: isEssential,
    };
  }

  async function ensureDraft(): Promise<number> {
    if (!token) throw new Error("no_token");
    if (preparedId !== null) return preparedId;
    const created = await adminCreateCampaign(buildInput(), token);
    if (imageFile) {
      await uploadCampaignImage(created.id, imageFile, token);
    }
    setPreparedId(created.id);
    await refresh();
    return created.id;
  }

  function resetForm() {
    setTitle("");
    setBody("");
    setCtaUrl("");
    setCtaLabel("");
    setImageFile(null);
    setPreparedId(null);
    setPreview(null);
  }

  async function run(fn: () => Promise<void>) {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await fn();
    } catch {
      setError(t("errGeneric"));
    } finally {
      setBusy(false);
    }
  }

  const onPreview = () =>
    run(async () => {
      const id = await ensureDraft();
      setPreview(await adminCampaignAudienceCount(id, token!));
    });

  const onSaveDraft = () =>
    run(async () => {
      await ensureDraft();
      setNote(t("savedDraft"));
    });

  const onSend = () =>
    run(async () => {
      const id = await ensureDraft();
      await adminSendCampaign(id, token!);
      await refresh();
      resetForm();
      setNote(t("sent"));
    });

  const canSubmit = title.trim().length > 0 && body.trim().length > 0;

  const columns: Column<Campaign>[] = [
    { key: "title", label: t("colTitle"), render: (c) => c.title },
    { key: "audience", label: t("colAudience"), render: (c) => t(`audience_${c.audience}`) },
    {
      key: "status",
      label: t("colStatus"),
      render: (c) => <span className={`${styles.pill} ${styles[c.status]}`}>{t(`status_${c.status}`)}</span>,
    },
    { key: "recipients_targeted", label: t("colTargeted"), render: (c) => c.recipients_targeted },
    {
      key: "counts",
      label: t("colDelivered"),
      render: (c) => `📣 ${c.inapp_created} · ✉ ${c.email_enqueued} · 💬 ${c.sms_enqueued}`,
    },
    {
      key: "sent_at",
      label: t("colSentAt"),
      render: (c) => (c.sent_at ? new Date(c.sent_at).toLocaleString() : "—"),
    },
  ];

  return (
    <div className={styles.page}>
      <h1 className={styles.h1}>{t("title")}</h1>

      <section className={styles.card}>
        <h2 className={styles.h2}>{t("composeHeading")}</h2>

        <fieldset className={styles.group}>
          <legend>{t("audienceLegend")}</legend>
          <div className={styles.radios}>
            {(["customers", "sellers", "both"] as NotificationAudience[]).map((a) => (
              <label key={a}>
                <input
                  type="radio"
                  name="audience"
                  checked={audience === a}
                  onChange={() => {
                    setAudience(a);
                    bump();
                  }}
                />
                {t(`audience_${a}`)}
              </label>
            ))}
          </div>
        </fieldset>

        {audience !== "both" && (
          <fieldset className={styles.group}>
            <legend>{t("filtersLegend")}</legend>
            <div className={styles.row}>
              <label className={styles.field}>
                {t("state")}
                <input value={stateName} onChange={(e) => { setStateName(e.target.value); bump(); }} />
              </label>
              <label className={styles.field}>
                {t("city")}
                <input value={city} onChange={(e) => { setCity(e.target.value); bump(); }} />
              </label>
            </div>
            <label className={styles.check}>
              <input type="checkbox" checked={newOnboarded} onChange={(e) => { setNewOnboarded(e.target.checked); bump(); }} />
              {t("newOnboarded")}
            </label>
            {audience === "sellers" && (
              <>
                <div className={styles.chips}>
                  {FEE_MODELS.map((m) => (
                    <label key={m} className={`${styles.chip} ${feeModels.includes(m) ? styles.chipOn : ""}`}>
                      <input
                        type="checkbox"
                        checked={feeModels.includes(m)}
                        onChange={(e) => {
                          setFeeModels((prev) => (e.target.checked ? [...prev, m] : prev.filter((x) => x !== m)));
                          bump();
                        }}
                      />
                      {t(`fee_${m}`)}
                    </label>
                  ))}
                </div>
                <label className={styles.check}>
                  <input type="checkbox" checked={expiringSoon} onChange={(e) => { setExpiringSoon(e.target.checked); bump(); }} />
                  {t("expiringSoon")}
                </label>
              </>
            )}
          </fieldset>
        )}

        <fieldset className={styles.group}>
          <legend>{t("channelsLegend")}</legend>
          <label className={styles.check}>
            <input type="checkbox" checked disabled />
            {t("channelInApp")}
          </label>
          <label className={styles.check}>
            <input type="checkbox" checked={email} onChange={(e) => { setEmail(e.target.checked); bump(); }} />
            {t("channelEmail")}
          </label>
          <label className={styles.check}>
            <input type="checkbox" checked={sms} onChange={(e) => { setSms(e.target.checked); bump(); }} />
            {t("channelSms")}
          </label>
          <label className={styles.check}>
            <input type="checkbox" checked={isEssential} onChange={(e) => { setIsEssential(e.target.checked); bump(); }} />
            {t("essential")}
          </label>
        </fieldset>

        <fieldset className={styles.group}>
          <legend>{t("contentLegend")}</legend>
          <label className={styles.field}>
            {t("titleLabel")}
            <input value={title} onChange={(e) => { setTitle(e.target.value); bump(); }} maxLength={140} />
          </label>
          <label className={styles.field}>
            {t("bodyLabel")}
            <textarea value={body} onChange={(e) => { setBody(e.target.value); bump(); }} rows={3} maxLength={2000} />
          </label>
          <label className={styles.field}>
            {t("imageLabel")}
            <input type="file" accept="image/*" onChange={(e) => { setImageFile(e.target.files?.[0] ?? null); bump(); }} />
          </label>
          <div className={styles.row}>
            <label className={styles.field}>
              {t("ctaLabelLabel")}
              <input value={ctaLabel} onChange={(e) => { setCtaLabel(e.target.value); bump(); }} maxLength={80} />
            </label>
            <label className={styles.field}>
              {t("ctaUrlLabel")}
              <input value={ctaUrl} onChange={(e) => { setCtaUrl(e.target.value); bump(); }} maxLength={500} />
            </label>
          </div>
        </fieldset>

        {preview && (
          <p className={styles.previewChip} role="status">
            {t("previewResult", { customers: preview.customers, sellers: preview.sellers })}
          </p>
        )}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {note && <p className={styles.note} role="status">{note}</p>}

        <div className={styles.actions}>
          <button className="btn btn-outline" onClick={onPreview} disabled={busy || !canSubmit}>
            {t("previewBtn")}
          </button>
          <button className="btn btn-outline" onClick={onSaveDraft} disabled={busy || !canSubmit}>
            {t("saveDraftBtn")}
          </button>
          <button className="btn btn-primary" onClick={onSend} disabled={busy || !canSubmit}>
            {t("sendBtn")}
          </button>
        </div>
      </section>

      <section className={styles.card}>
        <h2 className={styles.h2}>{t("historyHeading")}</h2>
        <DataTable columns={columns} data={campaigns} keyField="id" />
      </section>
    </div>
  );
}
