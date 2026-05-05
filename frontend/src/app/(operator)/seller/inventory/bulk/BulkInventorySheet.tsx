"use client";

import type { SheetRow } from "./page";
import styles from "./bulk.module.css";

export type IndexedRow = { row: SheetRow; originalIndex: number };

interface Props {
  rows: IndexedRow[];
  selectedIndices: Set<number>;
  onToggleSelect: (idx: number) => void;
  onPatchRow: (idx: number, patch: Partial<SheetRow>) => void;
  onRemoveRow: (idx: number) => void;
}

export function BulkInventorySheet({
  rows,
  selectedIndices,
  onToggleSelect,
  onPatchRow,
  onRemoveRow,
}: Props) {
  if (rows.length === 0) return null;

  return (
    <div className={styles.sheetWrap}>
      <table className={styles.sheet}>
        <thead>
          <tr>
            <th></th>
            <th>Product</th>
            <th>Subcategory</th>
            <th>Price (₹)</th>
            <th>Stock</th>
            <th>Avl</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ row, originalIndex }) => {
            const isNew = row.inventory_id === null;
            const dirty = row.dirty;
            const rowClass = dirty
              ? isNew
                ? styles.rowNew
                : styles.rowDirty
              : "";
            return (
              <tr key={`${row.product_id}-${originalIndex}`} className={rowClass}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIndices.has(originalIndex)}
                    onChange={() => onToggleSelect(originalIndex)}
                    aria-label={`Select ${row.product_name}`}
                  />
                </td>
                <td>{row.product_name}</td>
                <td>{row.subcategory_name}</td>
                <td>
                  <input
                    type="number"
                    className={
                      row.errors.price ? styles.cellErr : styles.cell
                    }
                    value={row.price}
                    min="0.01"
                    step="0.01"
                    onChange={(e) =>
                      onPatchRow(originalIndex, {
                        price: e.target.value,
                        dirty: true,
                        errors: validateCell(e.target.value, row.stock),
                      })
                    }
                  />
                  {row.errors.price && (
                    <div className={styles.cellErrMsg}>
                      {row.errors.price}
                    </div>
                  )}
                </td>
                <td>
                  <input
                    type="number"
                    className={
                      row.errors.stock ? styles.cellErr : styles.cell
                    }
                    value={row.stock}
                    min="0"
                    onChange={(e) =>
                      onPatchRow(originalIndex, {
                        stock: e.target.value,
                        dirty: true,
                        errors: validateCell(row.price, e.target.value),
                      })
                    }
                  />
                  {row.errors.stock && (
                    <div className={styles.cellErrMsg}>
                      {row.errors.stock}
                    </div>
                  )}
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={row.is_available}
                    onChange={(e) =>
                      onPatchRow(originalIndex, {
                        is_available: e.target.checked,
                        dirty: true,
                      })
                    }
                    aria-label={`Available ${row.product_name}`}
                  />
                </td>
                <td>
                  {isNew && (
                    <button
                      className="btn btn-outline"
                      onClick={() => onRemoveRow(originalIndex)}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function validateCell(price: string, stock: string): SheetRow["errors"] {
  const errors: SheetRow["errors"] = {};
  const p = parseFloat(price);
  if (isNaN(p) || p <= 0 || p > 999999) {
    errors.price = "Price must be > 0 and ≤ 999999";
  }
  const s = parseInt(stock, 10);
  if (isNaN(s) || s < 0) {
    errors.stock = "Stock must be ≥ 0";
  }
  return errors;
}
