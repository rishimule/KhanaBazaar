"use client";

import { useState, useMemo } from "react";
import DataTable, { Column } from "@/components/DataTable";
import Modal, { modalStyles } from "@/components/Modal";
import {
  mockInventories,
  mockProducts,
  getCategoryName,
} from "@/lib/mock-data";
import { InventoryWithProduct, MasterProduct } from "@/types";

import styles from "./page.module.css";

const SELLER_STORE_ID = 1;

export default function SellerInventoryPage() {
  const [inventory, setInventory] = useState<InventoryWithProduct[]>(
    () => [...(mockInventories[SELLER_STORE_ID] ?? [])]
  );
  const [editItem, setEditItem] = useState<InventoryWithProduct | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  // Form state
  const [formProductId, setFormProductId] = useState<number>(0);
  const [formPrice, setFormPrice] = useState("");
  const [formStock, setFormStock] = useState("");

  // Products not yet in inventory
  const availableProducts = useMemo(() => {
    const existingIds = new Set(inventory.map((i) => i.product_id));
    return mockProducts.filter((p) => !existingIds.has(p.id));
  }, [inventory]);

  const columns: Column<InventoryWithProduct>[] = [
    {
      key: "product_name",
      label: "Product",
      render: (row) => (
        <strong>{row.product.name}</strong>
      ),
    },
    {
      key: "category",
      label: "Category",
      render: (row) => getCategoryName(row.product.category_id),
    },
    {
      key: "price",
      label: "Price (₹)",
      render: (row) => `₹${row.price}`,
    },
    {
      key: "stock",
      label: "Stock",
      render: (row) => String(row.stock),
    },
    {
      key: "is_available",
      label: "Status",
      render: (row) => (
        <button
          className={`${styles.toggleBtn} ${
            row.is_available ? styles.toggleActive : styles.toggleInactive
          }`}
          onClick={() => toggleAvailability(row)}
        >
          {row.is_available ? "Available" : "Unavailable"}
        </button>
      ),
    },
  ];

  function toggleAvailability(item: InventoryWithProduct) {
    setInventory((prev) =>
      prev.map((i) =>
        i.id === item.id ? { ...i, is_available: !i.is_available } : i
      )
    );
  }

  function handleEdit(item: InventoryWithProduct) {
    setEditItem(item);
    setFormPrice(String(item.price));
    setFormStock(String(item.stock));
  }

  function handleSaveEdit() {
    if (!editItem) return;
    setInventory((prev) =>
      prev.map((i) =>
        i.id === editItem.id
          ? {
              ...i,
              price: parseFloat(formPrice) || i.price,
              stock: parseInt(formStock, 10) || i.stock,
            }
          : i
      )
    );
    setEditItem(null);
  }

  function handleDelete(item: InventoryWithProduct) {
    setInventory((prev) => prev.filter((i) => i.id !== item.id));
  }

  function openAdd() {
    setFormProductId(availableProducts[0]?.id ?? 0);
    setFormPrice("");
    setFormStock("");
    setShowAdd(true);
  }

  function handleAdd() {
    const product = mockProducts.find(
      (p) => p.id === formProductId
    ) as MasterProduct;
    if (!product) return;
    const newItem: InventoryWithProduct = {
      id: Date.now(),
      store_id: SELLER_STORE_ID,
      product_id: product.id,
      price: parseFloat(formPrice) || product.base_price,
      stock: parseInt(formStock, 10) || 0,
      is_available: true,
      product,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    setInventory((prev) => [...prev, newItem]);
    setShowAdd(false);
  }

  return (
    <>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <span className={styles.toolbarLeft}>
          {inventory.length} products in store
        </span>
        <button className={styles.addBtn} onClick={openAdd} disabled={availableProducts.length === 0}>
          + Add Product
        </button>
      </div>

      {/* Data table */}
      <DataTable
        columns={columns}
        data={inventory}
        keyField="id"
        onEdit={handleEdit}
        onDelete={handleDelete}
        emptyMessage="No inventory items yet. Add products from the master catalog."
      />

      {/* Edit Modal */}
      {editItem && (
        <Modal
          title={`Edit — ${editItem.product.name}`}
          onClose={() => setEditItem(null)}
          footer={
            <>
              <button
                className="btn btn-outline"
                onClick={() => setEditItem(null)}
              >
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleSaveEdit}>
                Save Changes
              </button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Price (₹)</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formPrice}
              onChange={(e) => setFormPrice(e.target.value)}
              min="0"
              step="0.01"
            />
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Stock</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formStock}
              onChange={(e) => setFormStock(e.target.value)}
              min="0"
            />
          </div>
        </Modal>
      )}

      {/* Add Modal */}
      {showAdd && (
        <Modal
          title="Add Product to Store"
          onClose={() => setShowAdd(false)}
          footer={
            <>
              <button
                className="btn btn-outline"
                onClick={() => setShowAdd(false)}
              >
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleAdd}>
                Add Product
              </button>
            </>
          }
        >
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Product</label>
            <select
              className={modalStyles.select}
              value={formProductId}
              onChange={(e) => setFormProductId(parseInt(e.target.value, 10))}
            >
              {availableProducts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — ₹{p.base_price}
                </option>
              ))}
            </select>
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Your Price (₹)</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formPrice}
              onChange={(e) => setFormPrice(e.target.value)}
              placeholder="Leave blank to use base price"
              min="0"
              step="0.01"
            />
          </div>
          <div className={modalStyles.formGroup}>
            <label className={modalStyles.label}>Stock Quantity</label>
            <input
              type="number"
              className={modalStyles.input}
              value={formStock}
              onChange={(e) => setFormStock(e.target.value)}
              placeholder="0"
              min="0"
            />
          </div>
        </Modal>
      )}
    </>
  );
}
