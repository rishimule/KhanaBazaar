"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
import { useState } from "react";
import { useTranslations } from "next-intl";
import { submitOrderReview } from "@/lib/orders";
import { useAuth } from "@/lib/AuthContext";
import type { Order } from "@/types";
import styles from "./OrderReviewForm.module.css";

interface Props {
  order: Order;
  onSubmitted: (next: Order) => void;
}

export default function OrderReviewForm({ order, onSubmitted }: Props) {
  const t = useTranslations("Order.review");
  const { token } = useAuth();
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (order.review !== null) {
    return (
      <div className={styles.summary}>
        {t("yourRating", { rating: order.review.rating })}
        {order.review.comment && (
          <p style={{ marginTop: 4 }}>{order.review.comment}</p>
        )}
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || rating < 1) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await submitOrderReview(token, order.id, rating, comment || null);
      onSubmitted({
        ...order,
        review: { rating: saved.rating, comment: saved.comment },
      });
    } catch (e) {
      const code = (e as { detail?: { error?: string } }).detail?.error;
      setError(code ? t(`error.${code}`) : t("error.generic"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.stars}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={n <= rating ? styles.starActive : styles.star}
            onClick={() => setRating(n)}
            aria-label={t("starAria", { n })}
          >
            ★
          </button>
        ))}
      </div>
      <textarea
        className={styles.textarea}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder={t("commentPlaceholder")}
        maxLength={2000}
      />
      <button className="btn btn-primary" type="submit" disabled={busy || rating < 1}>
        {t("submit")}
      </button>
      {error && <div className={styles.error}>{error}</div>}
    </form>
  );
}
