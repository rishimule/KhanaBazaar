// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"use client";
import {
  fmtTime,
  InboxHeader,
  LoginGate,
  NewMessagesBanner,
  Pager,
  SearchBar,
} from "../_shared/components";
import styles from "../_shared/inbox.module.css";
import { useInbox } from "../_shared/useInbox";

interface DevWhatsApp {
  id: number;
  created_at: string;
  to_phone: string;
  body: string;
  template: string | null;
  category: string | null;
}

export default function DevWhatsAppPage() {
  const inbox = useInbox<DevWhatsApp>("whatsapp");

  if (!inbox.basic) {
    return <LoginGate onAuthed={inbox.login} />;
  }

  return (
    <div className={styles.page}>
      <InboxHeader title="Dev Mailbox · WhatsApp" onLogout={inbox.logout} />
      <SearchBar
        value={inbox.q}
        onChange={inbox.setQ}
        placeholder="Search phone, body, template, category…"
      />
      <NewMessagesBanner count={inbox.newCount} onClick={inbox.loadNew} />
      {inbox.error && <div className={styles.error}>{inbox.error}</div>}
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Time</th>
            <th>To</th>
            <th>Template</th>
            <th>Category</th>
            <th>Body</th>
          </tr>
        </thead>
        <tbody>
          {inbox.items.map((m) => (
            <tr key={m.id}>
              <td className={styles.muted}>{fmtTime(m.created_at)}</td>
              <td className={styles.mono}>{m.to_phone}</td>
              <td className={styles.mono}>{m.template ?? "—"}</td>
              <td className={styles.muted}>{m.category ?? "—"}</td>
              <td>{m.body}</td>
            </tr>
          ))}
          {!inbox.loading && inbox.items.length === 0 && (
            <tr>
              <td colSpan={5} className={styles.muted}>
                No messages.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <Pager
        page={inbox.page}
        pageSize={inbox.pageSize}
        total={inbox.total}
        onPage={inbox.setPage}
        onRefresh={inbox.refresh}
      />
    </div>
  );
}
