"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import DataTable, { Column } from "@/components/DataTable";
import Modal, { modalStyles } from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { get, post, put, del } from "@/lib/api";
import { Category, MasterProduct, Service } from "@/types";
import styles from "../products/page.module.css";
import mobileStyles from "@/components/DataTableCard.module.css";

export default function AdminCategoriesPage() {
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<MasterProduct[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [fetching, setFetching] = useState(true);
  const [editItem, setEditItem] = useState<Category | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formServiceId, setFormServiceId] = useState<number | null>(null);

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      Promise.all([
        get<Category[]>("/api/v1/catalog/categories", token),
        get<MasterProduct[]>("/api/v1/catalog/products", token),
        get<Service[]>("/api/v1/catalog/services", token),
      ])
        .then(([cats, prods, svcs]) => {
          setCategories(cats);
          setProducts(prods);
          setServices(svcs);
        })
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [authLoading, dbUser, token, router]);

  const getServiceName = (svcId: number) =>
    services.find((s) => s.id === svcId)?.name ?? "—";

  const columns: Column<Category>[] = [
    { key: "name", label: "Category Name", render: (row) => <strong>{row.name}</strong> },
    {
      key: "service_id",
      label: "Service",
      render: (row) => (
        <span className={styles.categoryBadge}>{getServiceName(row.service_id)}</span>
      ),
    },
    {
      key: "description",
      label: "Description",
      render: (row) => row.description || "—",
    },
    {
      key: "products",
      label: "Products",
      render: (row) => {
        const count = products.filter((p) => p.category_id === row.id).length;
        return `${count} products`;
      },
    },
  ];

  function handleEdit(item: Category) {
    setEditItem(item);
    setFormName(item.name);
    setFormDesc(item.description ?? "");
  }

  async function handleSaveEdit() {
    if (!editItem || !token) return;
    try {
      const updated = await put<Category>(
        `/api/v1/catalog/categories/${editItem.id}`,
        { name: formName || editItem.name, description: formDesc || editItem.description },
        token
      );
      setCategories((prev) =>
        prev.map((c) => (c.id === editItem.id ? updated : c))
      );
      setEditItem(null);
    } catch { /* silent */ }
  }

  async function handleDelete(item: Category) {
    if (!token) return;
    try {
      await del(`/api/v1/catalog/categories/${item.id}`, token);
      setCategories((prev) => prev.filter((c) => c.id !== item.id));
    } catch { /* silent */ }
  }

  function openAdd() {
    setFormName("");
    setFormDesc("");
    setFormServiceId(services[0]?.id ?? null);
    setShowAdd(true);
  }

  async function handleAdd() {
    if (!formName.trim() || !token || formServiceId === null) return;
    try {
      const created = await post<Category>(
        "/api/v1/catalog/categories",
        {
          name: formName.trim(),
          description: formDesc.trim() || undefined,
          service_id: formServiceId,
        },
        token
      );
      setCategories((prev) => [...prev, created]);
      setShowAdd(false);
    } catch { /* silent */ }
  }

  if (authLoading || fetching) {
    return <div style={{ padding: "2rem", textAlign: "center", color: "var(--color-neutral-500)" }}>Loading…</div>;
  }

  return (
    <>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <span className={styles.toolbarCount}>
          {categories.length} categories
        </span>
        <button className={styles.addBtn} onClick={openAdd}>
          + Add Category
        </button>
      </div>

      {/* Data table */}
      <DataTable
        columns={columns}
        data={categories}
        keyField="id"
        onEdit={handleEdit}
        onDelete={handleDelete}
        emptyMessage="No categories yet. Add one to get started."
        mobileCardRender={(c) => {
          const productCount = products.filter((p) => p.category_id === c.id).length;
          return (
            <>
              <div className={mobileStyles.cardTopRow}>
                <span className={mobileStyles.cardTitle}>{c.name}</span>
                <span className={styles.categoryBadge}>{getServiceName(c.service_id)}</span>
              </div>
              {c.description && (
                <p className={mobileStyles.cardSubtitle}>{c.description}</p>
              )}
              <div className={mobileStyles.cardMeta}>
                {productCount} product{productCount === 1 ? "" : "s"}
              </div>
            </>
          );
        }}
      />

      {/* Edit Modal */}
      {editItem && (
        <Modal
          title={`Edit — ${editItem.name}`}
          onClose={() => setEditItem(null)}
          footer={
            <>
              <button className="btn btn-outline" onClick={() => setEditItem(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSaveEdit}>Save</button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Category Name</label>
            <input className={modalStyles.input} value={formName} onChange={(e) => setFormName(e.target.value)} />
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Description</label>
            <textarea className={modalStyles.textarea} value={formDesc} onChange={(e) => setFormDesc(e.target.value)} />
          </div>
        </Modal>
      )}

      {/* Add Modal */}
      {showAdd && (
        <Modal
          title="Add New Category"
          onClose={() => setShowAdd(false)}
          footer={
            <>
              <button className="btn btn-outline" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleAdd}>Add Category</button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Service</label>
            <select
              className={modalStyles.select}
              value={formServiceId ?? ""}
              onChange={(e) => setFormServiceId(e.target.value ? parseInt(e.target.value, 10) : null)}
            >
              {services.length === 0 && <option value="">No services available</option>}
              {services.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Category Name</label>
            <input className={modalStyles.input} value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="e.g., Spices & Masala" />
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Description</label>
            <textarea className={modalStyles.textarea} value={formDesc} onChange={(e) => setFormDesc(e.target.value)} placeholder="Brief description of this category" />
          </div>
        </Modal>
      )}
    </>
  );
}
