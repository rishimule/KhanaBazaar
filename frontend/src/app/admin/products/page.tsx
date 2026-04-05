"use client";

import { useState, useMemo } from "react";
import DataTable, { Column } from "@/components/DataTable";
import Modal, { modalStyles } from "@/components/Modal";
import { mockProducts, mockCategories, getCategoryName } from "@/lib/mock-data";
import { MasterProduct } from "@/types";
import styles from "./page.module.css";

export default function AdminProductsPage() {
  const [products, setProducts] = useState<MasterProduct[]>(() => [
    ...mockProducts,
  ]);
  const [editItem, setEditItem] = useState<MasterProduct | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [filterCat, setFilterCat] = useState<number | null>(null);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formCat, setFormCat] = useState<number>(1);
  const [formPrice, setFormPrice] = useState("");

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
    {
      key: "base_price",
      label: "Base Price",
      render: (row) => `₹${row.base_price}`,
    },
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

  function handleSaveEdit() {
    if (!editItem) return;
    setProducts((prev) =>
      prev.map((p) =>
        p.id === editItem.id
          ? {
              ...p,
              name: formName || p.name,
              description: formDesc,
              category_id: formCat,
              base_price: parseFloat(formPrice) || p.base_price,
              updated_at: new Date().toISOString(),
            }
          : p
      )
    );
    setEditItem(null);
  }

  function handleDelete(item: MasterProduct) {
    setProducts((prev) => prev.filter((p) => p.id !== item.id));
  }

  function openAdd() {
    setFormName("");
    setFormDesc("");
    setFormCat(mockCategories[0]?.id ?? 1);
    setFormPrice("");
    setShowAdd(true);
  }

  function handleAdd() {
    if (!formName.trim()) return;
    const newProduct: MasterProduct = {
      id: Date.now(),
      name: formName.trim(),
      description: formDesc.trim(),
      category_id: formCat,
      base_price: parseFloat(formPrice) || 0,
      image_url: undefined,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    setProducts((prev) => [...prev, newProduct]);
    setShowAdd(false);
  }

  return (
    <>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <span className={styles.toolbarCount}>
            {filteredProducts.length} products
          </span>
          <select
            className={styles.filterSelect}
            value={filterCat ?? ""}
            onChange={(e) =>
              setFilterCat(e.target.value ? parseInt(e.target.value, 10) : null)
            }
          >
            <option value="">All Categories</option>
            {mockCategories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <button className={styles.addBtn} onClick={openAdd}>
          + Add Product
        </button>
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
}: {
  name: string; setName: (v: string) => void;
  desc: string; setDesc: (v: string) => void;
  cat: number; setCat: (v: number) => void;
  price: string; setPrice: (v: string) => void;
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
          {mockCategories.map((c) => (
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
