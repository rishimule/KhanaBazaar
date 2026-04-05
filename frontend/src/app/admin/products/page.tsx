"use client";

import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import DataTable, { Column } from "@/components/DataTable";
import Modal, { modalStyles } from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { get, post, put, del } from "@/lib/api";
import { MasterProduct, Category } from "@/types";
import styles from "./page.module.css";

export default function AdminProductsPage() {
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [products, setProducts] = useState<MasterProduct[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [fetching, setFetching] = useState(true);
  const [editItem, setEditItem] = useState<MasterProduct | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [filterCat, setFilterCat] = useState<number | null>(null);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formCat, setFormCat] = useState<number>(1);
  const [formPrice, setFormPrice] = useState("");

  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "admin")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      Promise.all([
        get<MasterProduct[]>("/api/v1/catalog/products", token),
        get<Category[]>("/api/v1/catalog/categories", token),
      ])
        .then(([prods, cats]) => {
          setProducts(prods);
          setCategories(cats);
        })
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [authLoading, dbUser, token, router]);

  const getCategoryName = (catId: number) =>
    categories.find((c) => c.id === catId)?.name ?? "Other";

  const filteredProducts = useMemo(() => {
    if (filterCat === null) return products;
    return products.filter((p) => p.category_id === filterCat);
  }, [products, filterCat]);

  const columns: Column<MasterProduct>[] = [
    { key: "name", label: "Product Name", render: (row) => <strong>{row.name}</strong> },
    {
      key: "category_id",
      label: "Category",
      render: (row) => (
        <span className={styles.categoryBadge}>
          {getCategoryName(row.category_id)}
        </span>
      ),
    },
    { key: "base_price", label: "Base Price", render: (row) => `₹${row.base_price}` },
    {
      key: "description",
      label: "Description",
      render: (row) => {
        const desc = row.description || "—";
        return desc.length > 60 ? desc.slice(0, 57) + "..." : desc;
      },
    },
  ];

  function handleEdit(item: MasterProduct) {
    setEditItem(item);
    setFormName(item.name);
    setFormDesc(item.description);
    setFormCat(item.category_id);
    setFormPrice(String(item.base_price));
  }

  async function handleSaveEdit() {
    if (!editItem || !token) return;
    try {
      const updated = await put<MasterProduct>(
        `/api/v1/catalog/products/${editItem.id}`,
        {
          name: formName || editItem.name,
          description: formDesc,
          category_id: formCat,
          base_price: parseFloat(formPrice) || editItem.base_price,
        },
        token
      );
      setProducts((prev) =>
        prev.map((p) => (p.id === editItem.id ? updated : p))
      );
      setEditItem(null);
    } catch { /* silent */ }
  }

  async function handleDelete(item: MasterProduct) {
    if (!token) return;
    try {
      await del(`/api/v1/catalog/products/${item.id}`, token);
      setProducts((prev) => prev.filter((p) => p.id !== item.id));
    } catch { /* silent */ }
  }

  function openAdd() {
    setFormName("");
    setFormDesc("");
    setFormCat(categories[0]?.id ?? 1);
    setFormPrice("");
    setShowAdd(true);
  }

  async function handleAdd() {
    if (!formName.trim() || !token) return;
    try {
      const created = await post<MasterProduct>(
        "/api/v1/catalog/products",
        {
          name: formName.trim(),
          description: formDesc.trim(),
          category_id: formCat,
          base_price: parseFloat(formPrice) || 0,
        },
        token
      );
      setProducts((prev) => [...prev, created]);
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
        <div className={styles.toolbarLeft}>
          <span className={styles.toolbarCount}>{filteredProducts.length} products</span>
          <select
            className={styles.filterSelect}
            value={filterCat ?? ""}
            onChange={(e) =>
              setFilterCat(e.target.value ? parseInt(e.target.value, 10) : null)
            }
          >
            <option value="">All Categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <button className={styles.addBtn} onClick={openAdd}>+ Add Product</button>
      </div>

      {/* Data table */}
      <DataTable
        columns={columns}
        data={filteredProducts}
        keyField="id"
        onEdit={handleEdit}
        onDelete={handleDelete}
        emptyMessage="No products in the catalog yet."
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
          <ProductForm
            name={formName} setName={setFormName}
            desc={formDesc} setDesc={setFormDesc}
            cat={formCat} setCat={setFormCat}
            price={formPrice} setPrice={setFormPrice}
            categories={categories}
          />
        </Modal>
      )}

      {/* Add Modal */}
      {showAdd && (
        <Modal
          title="Add New Product"
          onClose={() => setShowAdd(false)}
          footer={
            <>
              <button className="btn btn-outline" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleAdd}>Add Product</button>
            </>
          }
        >
          <ProductForm
            name={formName} setName={setFormName}
            desc={formDesc} setDesc={setFormDesc}
            cat={formCat} setCat={setFormCat}
            price={formPrice} setPrice={setFormPrice}
            categories={categories}
          />
        </Modal>
      )}
    </>
  );
}

/** Shared form fields for add/edit */
function ProductForm({
  name, setName,
  desc, setDesc,
  cat, setCat,
  price, setPrice,
  categories,
}: {
  name: string; setName: (v: string) => void;
  desc: string; setDesc: (v: string) => void;
  cat: number; setCat: (v: number) => void;
  price: string; setPrice: (v: string) => void;
  categories: Category[];
}) {
  return (
    <>
      <div className={modalStyles.formGroup}>
        <label className={modalStyles.label}>Product Name</label>
        <input className={modalStyles.input} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className={modalStyles.formGroup}>
        <label className={modalStyles.label}>Description</label>
        <textarea className={modalStyles.textarea} value={desc} onChange={(e) => setDesc(e.target.value)} />
      </div>
      <div className={modalStyles.formGroup}>
        <label className={modalStyles.label}>Category</label>
        <select className={modalStyles.select} value={cat} onChange={(e) => setCat(parseInt(e.target.value, 10))}>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </div>
      <div className={modalStyles.formGroup}>
        <label className={modalStyles.label}>Base Price (₹)</label>
        <input type="number" className={modalStyles.input} value={price} onChange={(e) => setPrice(e.target.value)} min="0" step="0.01" />
      </div>
    </>
  );
}
