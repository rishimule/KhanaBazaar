import styles from "./DataTable.module.css";

export interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
}

interface Props<T> {
  columns: Column<T>[];
  data: T[];
  keyField: string;
  onEdit?: (row: T) => void;
  onDelete?: (row: T) => void;
  emptyMessage?: string;
}

export default function DataTable<T extends object>({
  columns,
  data,
  keyField,
  onEdit,
  onDelete,
  emptyMessage = "No data to display",
}: Props<T>) {
  if (data.length === 0) {
    return (
      <div className={styles.tableWrap}>
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>📋</div>
          <p className={styles.emptyText}>{emptyMessage}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key}>{col.label}</th>
            ))}
            {(onEdit || onDelete) && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => {
            const rec = row as Record<string, unknown>;
            return (
              <tr key={String(rec[keyField])}>
                {columns.map((col) => (
                  <td key={col.key}>
                    {col.render
                      ? col.render(row)
                      : String(rec[col.key] ?? "—")}
                  </td>
                ))}
                {(onEdit || onDelete) && (
                  <td>
                    <div className={styles.actions}>
                      {onEdit && (
                        <button
                          className={`${styles.actionBtn} ${styles.editBtn}`}
                          onClick={() => onEdit(row)}
                        >
                          Edit
                        </button>
                      )}
                      {onDelete && (
                        <button
                          className={`${styles.actionBtn} ${styles.deleteBtn}`}
                          onClick={() => onDelete(row)}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
