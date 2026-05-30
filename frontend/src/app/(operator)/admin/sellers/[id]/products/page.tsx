"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AdminReasonModal from "@/components/admin/AdminReasonModal";
import { useAuth } from "@/lib/AuthContext";
import { del, patch, put } from "@/lib/api";
import { fetchSellerHub, fetchSellerInventory } from "@/lib/adminActions";
import type { AdminInventoryRow, SellerHubSummary } from "@/types";

type Row = AdminInventoryRow;

export default function AdminProductsTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const t = useTranslations("Admin.sellerHub");
  const tc = useTranslations("Admin.common");
  const { token } = useAuth();
  const [hub, setHub] = useState<SellerHubSummary | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Row | null>(null);
  const [editing, setEditing] = useState<Row | null>(null);
  const [pausePrompt, setPausePrompt] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [h, inv] = await Promise.all([
        fetchSellerHub(Number(id), token),
        fetchSellerInventory(Number(id), token),
      ]);
      setHub(h);
      setRows(inv);
    } catch {
      setError(t("products.loadError"));
    }
  }, [id, token, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function savePriceStock(row: Row, price: number, stock: number) {
    if (!hub?.store_id || !token) return;
    await put(
      `/api/v1/stores/${hub.store_id}/inventory/${row.id}`,
      {
        product_id: row.product_id,
        price,
        stock,
        is_available: row.is_available,
      },
      token,
    );
    setEditing(null);
    await load();
  }

  async function doTogglePause(reason: string) {
    if (!hub || !token) return;
    await patch(
      `/api/v1/sellers/admin/${hub.seller_id}/store/pause`,
      { is_paused: !hub.store_paused, reason },
      token,
    );
    setPausePrompt(false);
    await load();
  }

  async function doDelete(reason: string) {
    if (!pendingDelete || !hub?.store_id || !token) return;
    const qs = new URLSearchParams({ reason }).toString();
    await del(
      `/api/v1/stores/${hub.store_id}/inventory/${pendingDelete.id}?${qs}`,
      token,
    );
    setPendingDelete(null);
    await load();
  }

  if (error) return <div>{error}</div>;
  if (!hub) return <div>{tc("loading")}</div>;

  if (!hub.store_id) {
    return (
      <div
        style={{
          padding: "2rem",
          background: "var(--color-neutral-50)",
          borderRadius: 8,
          textAlign: "center",
          color: "var(--color-neutral-600)",
        }}
      >
        {t("products.noStore")}
      </div>
    );
  }

  const blocked = hub.verification_status !== "approved";

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.75rem",
          marginBottom: "0.75rem",
        }}
      >
        <h2 style={{ margin: 0 }}>
          {t("products.heading", { n: rows.length })}
          {hub.store_paused && (
            <span
              style={{
                marginLeft: "0.6rem",
                fontSize: "0.7rem",
                fontWeight: 600,
                padding: "2px 8px",
                borderRadius: 999,
                background: "rgba(245, 158, 11, 0.18)",
                color: "var(--color-neutral-900)",
                verticalAlign: "middle",
              }}
            >
              {t("products.closedBadge")}
            </span>
          )}
        </h2>
        <button
          className="btn btn-outline"
          disabled={blocked}
          onClick={() => setPausePrompt(true)}
        >
          {hub.store_paused ? t("products.reopenStore") : t("products.closeStore")}
        </button>
      </div>
      {blocked && (
        <div
          style={{
            padding: "0.6rem 0.9rem",
            background: "rgba(245, 158, 11, 0.14)",
            border: "1px solid var(--color-warning)",
            borderRadius: 6,
            marginBottom: "0.75rem",
            color: "var(--color-neutral-900)",
          }}
        >
          {t("products.writesBlocked")}
        </div>
      )}
      <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.92rem",
        }}
      >
        <thead>
          <tr style={{ background: "var(--color-neutral-50)" }}>
            <th style={cellHead}>{t("products.col.inv")}</th>
            <th style={cellHead}>{t("products.col.product")}</th>
            <th style={cellHead}>{t("products.col.price")}</th>
            <th style={cellHead}>{t("products.col.stock")}</th>
            <th style={cellHead}>{t("products.col.available")}</th>
            <th style={cellHead}>{t("products.col.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={cell}>{r.id}</td>
              <td style={cell}>
                <div style={{ fontWeight: 500 }}>{r.product_name}</div>
                <div
                  style={{
                    color: "var(--color-neutral-500)",
                    fontSize: "0.78rem",
                  }}
                >
                  #{r.product_id}
                  {r.product_brand ? ` · ${r.product_brand}` : ""}
                  {r.product_unit ? ` · ${r.product_unit}` : ""}
                </div>
              </td>
              <td style={cell}>₹{r.price.toFixed(2)}</td>
              <td style={cell}>{r.stock}</td>
              <td style={cell}>{r.is_available ? "✅" : "—"}</td>
              <td style={cell}>
                <button
                  className="btn btn-outline"
                  disabled={blocked}
                  onClick={() => setEditing(r)}
                  style={{ marginRight: 6 }}
                >
                  {tc("edit")}
                </button>
                <button
                  className="btn btn-danger"
                  disabled={blocked}
                  onClick={() => setPendingDelete(r)}
                >
                  {tc("delete")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      {editing && (
        <EditModal
          row={editing}
          onClose={() => setEditing(null)}
          onSave={savePriceStock}
        />
      )}

      {pausePrompt && (
        <AdminReasonModal
          title={
            hub.store_paused
              ? t("products.reopenTitle")
              : t("products.closeTitle")
          }
          description={
            hub.store_paused
              ? t("products.reopenDesc")
              : t("products.closeDesc")
          }
          confirmLabel={
            hub.store_paused
              ? t("products.reopenStore")
              : t("products.closeStore")
          }
          destructive={false}
          onConfirm={doTogglePause}
          onClose={() => setPausePrompt(false)}
        />
      )}

      {pendingDelete && (
        <AdminReasonModal
          title={t("products.deleteTitle", { name: pendingDelete.product_name })}
          description={t("products.deleteDesc", {
            name: pendingDelete.product_name,
            id: pendingDelete.id,
          })}
          confirmLabel={tc("delete")}
          destructive
          onConfirm={doDelete}
          onClose={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}

function EditModal({
  row,
  onClose,
  onSave,
}: {
  row: Row;
  onClose: () => void;
  onSave: (row: Row, price: number, stock: number) => Promise<void>;
}) {
  const t = useTranslations("Admin.sellerHub");
  const tc = useTranslations("Admin.common");
  const [price, setPrice] = useState(row.price);
  const [stock, setStock] = useState(row.stock);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await onSave(row, price, stock);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.45)",
        display: "grid",
        placeItems: "center",
        zIndex: 100,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          padding: "1.25rem",
          width: "min(420px, 92vw)",
          borderRadius: 10,
          display: "grid",
          gap: "0.75rem",
        }}
      >
        <h3>{t("products.editTitle", { name: row.product_name })}</h3>
        <div style={{ color: "var(--color-neutral-500)", fontSize: "0.85rem" }}>
          {t("products.editSubtitle", { inv: row.id, product: row.product_id })}
        </div>
        <label>
          {t("products.col.price")}
          <input
            type="number"
            step="0.01"
            value={price}
            onChange={(e) => setPrice(Number(e.target.value))}
            style={inp}
          />
        </label>
        <label>
          {t("products.col.stock")}
          <input
            type="number"
            value={stock}
            onChange={(e) => setStock(Number(e.target.value))}
            style={inp}
          />
        </label>
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button className="btn btn-outline" onClick={onClose} disabled={busy}>
            {tc("cancel")}
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? tc("saving") : tc("save")}
          </button>
        </div>
      </div>
    </div>
  );
}

const cellHead: React.CSSProperties = {
  textAlign: "left",
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid var(--color-neutral-200)",
  fontWeight: 500,
};
const cell: React.CSSProperties = {
  padding: "0.45rem 0.75rem",
  borderBottom: "1px solid var(--color-neutral-100)",
};
const inp: React.CSSProperties = {
  display: "block",
  width: "100%",
  padding: "0.45rem",
  marginTop: "0.25rem",
  border: "1px solid var(--color-neutral-300)",
  borderRadius: 6,
};
