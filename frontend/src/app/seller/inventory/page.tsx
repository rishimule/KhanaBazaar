"use client";

import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import DataTable, { Column } from "@/components/DataTable";
import Modal, { modalStyles } from "@/components/Modal";
import { useAuth } from "@/lib/AuthContext";
import { get, post, put, del } from "@/lib/api";
import { Store, StoreInventory, MasterProduct, Category } from "@/types";

import styles from "./page.module.css";

/** Enriched inventory with product info */
interface InventoryWithProduct extends StoreInventory {
  product: MasterProduct;
}

export default function SellerInventoryPage() {
  const router = useRouter();
  const { dbUser, token, loading: authLoading } = useAuth();

  const [store, setStore] = useState<Store | null>(null);
  const [inventory, setInventory] = useState<InventoryWithProduct[]>([]);
  const [allProducts, setAllProducts] = useState<MasterProduct[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [fetching, setFetching] = useState(true);

  const [editItem, setEditItem] = useState<InventoryWithProduct | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [formProductId, setFormProductId] = useState<number>(0);
  const [formPrice, setFormPrice] = useState("");
  const [formStock, setFormStock] = useState("");

  // Fetch data
  useEffect(() => {
    if (!authLoading && (!dbUser || dbUser.role !== "seller")) {
      router.push(dbUser ? "/" : "/login");
      return;
    }
    if (!authLoading && dbUser && token) {
      Promise.all([
        get<Store[]>("/api/v1/stores/my", token),
        get<MasterProduct[]>("/api/v1/catalog/products"),
        get<Category[]>("/api/v1/catalog/categories"),
      ])
        .then(async ([myStores, products, cats]) => {
          setAllProducts(products);
          setCategories(cats);
          if (myStores.length > 0) {
            const s = myStores[0];
            setStore(s);
            const inv = await get<StoreInventory[]>(
              `/api/v1/stores/${s.id}/inventory/all`,
              token
            );
            const productMap = new Map(products.map((p) => [p.id, p]));
            setInventory(
              inv
                .map((i) => ({ ...i, product: productMap.get(i.product_id)! }))
                .filter((i) => i.product)
            );
          }
        })
        .catch(() => {})
        .finally(() => setFetching(false));
    }
  }, [authLoading, dbUser, token, router]);

  const getCategoryName = (catId: number) =>
    categories.find((c) => c.id === catId)?.name ?? "Other";

  // Products not yet in inventory
  const availableProducts = useMemo(() => {
    const existingIds = new Set(inventory.map((i) => i.product_id));
    return allProducts.filter((p) => !existingIds.has(p.id));
  }, [inventory, allProducts]);

  const columns: Column<InventoryWithProduct>[] = [
    {
      key: "product_name",
      label: "Product",
      render: (row) => <strong>{row.product.name}</strong>,
    },
    {
      key: "category",
      label: "Category",
      render: (row) => getCategoryName(row.product.category_id),
    },
    { key: "price", label: "Price (₹)", render: (row) => `₹${row.price}` },
    { key: "stock", label: "Stock", render: (row) => String(row.stock) },
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

  async function toggleAvailability(item: InventoryWithProduct) {
    if (!store || !token) return;
    try {
      await put(
        `/api/v1/stores/${store.id}/inventory/${item.id}`,
        { is_available: !item.is_available, price: item.price, stock: item.stock },
        token
      );
      setInventory((prev) =>
        prev.map((i) =>
          i.id === item.id ? { ...i, is_available: !i.is_available } : i
        )
      );
    } catch { /* silent */ }
  }

  function handleEdit(item: InventoryWithProduct) {
    setEditItem(item);
    setFormPrice(String(item.price));
    setFormStock(String(item.stock));
  }

  async function handleSaveEdit() {
    if (!editItem || !store || !token) return;
    try {
      await put(
        `/api/v1/stores/${store.id}/inventory/${editItem.id}`,
        {
          price: parseFloat(formPrice) || editItem.price,
          stock: parseInt(formStock, 10) ?? editItem.stock,
          is_available: editItem.is_available,
        },
        token
      );
      setInventory((prev) =>
        prev.map((i) =>
          i.id === editItem.id
            ? {
                ...i,
                price: parseFloat(formPrice) || i.price,
                stock: parseInt(formStock, 10) ?? i.stock,
              }
            : i
        )
      );
      setEditItem(null);
    } catch { /* silent */ }
  }

  async function handleDelete(item: InventoryWithProduct) {
    if (!store || !token) return;
    try {
      await del(`/api/v1/stores/${store.id}/inventory/${item.id}`, token);
      setInventory((prev) => prev.filter((i) => i.id !== item.id));
    } catch { /* silent */ }
  }

  function openAdd() {
    setFormProductId(availableProducts[0]?.id ?? 0);
    setFormPrice("");
    setFormStock("");
    setShowAdd(true);
  }

  async function handleAdd() {
    if (!store || !token) return;
    const product = allProducts.find((p) => p.id === formProductId);
    if (!product) return;
    try {
      const created = await post<StoreInventory>(
        `/api/v1/stores/${store.id}/inventory`,
        {
          product_id: product.id,
          price: parseFloat(formPrice) || product.base_price,
          stock: parseInt(formStock, 10) || 0,
          is_available: true,
        },
        token
      );
      setInventory((prev) => [...prev, { ...created, product }]);
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
              <button className="btn btn-outline" onClick={() => setEditItem(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSaveEdit}>Save Changes</button>
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
              <button className="btn btn-outline" onClick={() => setShowAdd(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleAdd}>Add Product</button>
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
