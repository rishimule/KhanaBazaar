"use client";

import { useState } from "react";
import DataTable, { Column } from "@/components/DataTable";
import Modal, { modalStyles } from "@/components/Modal";
import { mockCategories, mockProducts } from "@/lib/mock-data";
import { Category } from "@/types";
import styles from "../products/page.module.css";

export default function AdminCategoriesPage() {
  const [categories, setCategories] = useState<Category[]>(() => [
    ...mockCategories,
  ]);
  const [editItem, setEditItem] = useState<Category | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");

  const columns: Column<Category>[] = [
    { key: "name", label: "Category Name", render: (row) => <strong>{row.name}</strong> },
    {
      key: "description",
      label: "Description",
      render: (row) => row.description || "—",
    },
    {
      key: "products",
      label: "Products",
      render: (row) => {
        const count = mockProducts.filter(
          (p) => p.category_id === row.id
        ).length;
        return `${count} products`;
      },
    },
  ];

  function handleEdit(item: Category) {
    setEditItem(item);
    setFormName(item.name);
    setFormDesc(item.description ?? "");
  }

  function handleSaveEdit() {
    if (!editItem) return;
    setCategories((prev) =>
      prev.map((c) =>
        c.id === editItem.id
          ? {
              ...c,
              name: formName || c.name,
              description: formDesc || c.description,
              updated_at: new Date().toISOString(),
            }
          : c
      )
    );
    setEditItem(null);
  }

  function handleDelete(item: Category) {
    setCategories((prev) => prev.filter((c) => c.id !== item.id));
  }

  function openAdd() {
    setFormName("");
    setFormDesc("");
    setShowAdd(true);
  }

  function handleAdd() {
    if (!formName.trim()) return;
    const newCat: Category = {
      id: Date.now(),
      name: formName.trim(),
      description: formDesc.trim() || undefined,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    setCategories((prev) => [...prev, newCat]);
    setShowAdd(false);
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
