// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
"use client";
import { useState } from "react";

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

interface DevEmail {
  id: number;
  created_at: string;
  to_email: string;
  subject: string;
  body_text: string;
  body_html: string | null;
  reply_to: string | null;
  category: string | null;
}

export default function DevEmailsPage() {
  const inbox = useInbox<DevEmail>("emails");
  const [selected, setSelected] = useState<DevEmail | null>(null);

  if (!inbox.basic) {
    return <LoginGate onAuthed={() => inbox.refresh()} />;
  }

  return (
    <div className={styles.page}>
      <InboxHeader title="Dev Mailbox · Emails" onLogout={inbox.logout} />
      <SearchBar
        value={inbox.q}
        onChange={inbox.setQ}
        placeholder="Search recipient, subject, category…"
      />
      <NewMessagesBanner count={inbox.newCount} onClick={inbox.loadNew} />
      {inbox.error && <div className={styles.error}>{inbox.error}</div>}
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Time</th>
            <th>To</th>
            <th>Subject</th>
            <th>Category</th>
          </tr>
        </thead>
        <tbody>
          {inbox.items.map((m) => (
            <tr key={m.id} className={styles.row} onClick={() => setSelected(m)}>
              <td className={styles.muted}>{fmtTime(m.created_at)}</td>
              <td className={styles.mono}>{m.to_email}</td>
              <td>{m.subject}</td>
              <td className={styles.muted}>{m.category ?? "—"}</td>
            </tr>
          ))}
          {!inbox.loading && inbox.items.length === 0 && (
            <tr>
              <td colSpan={4} className={styles.muted}>
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
      {selected && (
        <div className={styles.overlay} onClick={() => setSelected(null)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <button className={styles.closeBtn} onClick={() => setSelected(null)}>
              Close
            </button>
            <h2>{selected.subject}</h2>
            <div className={styles.kv}>
              <span>To</span> {selected.to_email}
            </div>
            <div className={styles.kv}>
              <span>Reply-to</span> {selected.reply_to ?? "—"}
            </div>
            <div className={styles.kv}>
              <span>Category</span> {selected.category ?? "—"}
            </div>
            <div className={styles.kv}>
              <span>Time</span> {fmtTime(selected.created_at)}
            </div>
            {selected.body_html ? (
              <iframe
                className={styles.iframe}
                sandbox=""
                srcDoc={selected.body_html}
                title="email-html"
              />
            ) : (
              <div className={styles.bodyText}>{selected.body_text}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
