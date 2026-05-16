"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { use, useCallback, useEffect, useState } from "react";
import AdminReasonModal from "@/components/admin/AdminReasonModal";
import { useAuth } from "@/lib/AuthContext";
import { del, get, put } from "@/lib/api";
import { fetchSellerHub } from "@/lib/adminActions";
import type { SellerHubSummary, StoreInventory } from "@/types";

type Row = StoreInventory;

export default function AdminProductsTab({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { token } = useAuth();
  const [hub, setHub] = useState<SellerHubSummary | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Row | null>(null);
  const [editing, setEditing] = useState<Row | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const h = await fetchSellerHub(Number(id), token);
      setHub(h);
      if (h.store_id) {
        const inv = await get<Row[]>(
          `/api/v1/stores/${h.store_id}/inventory/all`,
          token,
        );
        setRows(inv);
      }
    } catch {
      setError("Failed to load inventory");
    }
  }, [id, token]);

  useEffect(() => {
    load();
  }, [load]);

  async function savePriceStock(row: Row, price: number, stock: number) {
    if (!hub?.store_id || !token) return;
    await put(
      `/api/v1/stores/${hub.store_id}/inventory/${row.id}`,
      { ...row, price, stock },
      token,
    );
    setEditing(null);
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
  if (!hub) return <div>Loading…</div>;

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
        Seller has no store yet — products tab is empty.
      </div>
    );
  }

  const blocked = hub.verification_status !== "approved";

  return (
    <div>
      <h2 style={{ marginBottom: "0.75rem" }}>
        Products ({rows.length})
      </h2>
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
          Seller is not active — writes disabled.
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
            <th style={cellHead}>Inv #</th>
            <th style={cellHead}>Product ID</th>
            <th style={cellHead}>Price</th>
            <th style={cellHead}>Stock</th>
            <th style={cellHead}>Available</th>
            <th style={cellHead}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={cell}>{r.id}</td>
              <td style={cell}>{r.product_id}</td>
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
                  Edit
                </button>
                <button
                  className="btn btn-danger"
                  disabled={blocked}
                  onClick={() => setPendingDelete(r)}
                >
                  Delete
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

      {pendingDelete && (
        <AdminReasonModal
          title={`Delete inventory #${pendingDelete.id}?`}
          description="This removes the listing from the seller's store. Reason is recorded in the audit log."
          confirmLabel="Delete"
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
        <h3>Edit inventory #{row.id}</h3>
        <label>
          Price
          <input
            type="number"
            step="0.01"
            value={price}
            onChange={(e) => setPrice(Number(e.target.value))}
            style={inp}
          />
        </label>
        <label>
          Stock
          <input
            type="number"
            value={stock}
            onChange={(e) => setStock(Number(e.target.value))}
            style={inp}
          />
        </label>
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button className="btn btn-outline" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? "Saving…" : "Save"}
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
