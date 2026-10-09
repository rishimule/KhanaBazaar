"use client";
// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import type { Ref } from "react";
import { INDIAN_PHONE_PREFIX, nationalDigits } from "@/lib/indianPhone";
import styles from "./IndianPhoneField.module.css";

interface Props {
  id: string;
  /** The digits typed so far (no prefix); see `nationalDigits`. */
  value: string;
  onChange: (digits: string) => void;
  name?: string;
  inputRef?: Ref<HTMLInputElement>;
  disabled?: boolean;
  autoFocus?: boolean;
  invalid?: boolean;
  /** id of the hint/error line under the field. */
  describedBy?: string;
  /** Page-specific look for the frame and the input (sizes, radius). */
  className?: string;
  inputClassName?: string;
}

/** `+91` prefix + national-number input for the signup screens. No
 * `maxLength`: the browser would cut a pasted `+91 98765 43210` before
 * `nationalDigits` could strip the country code. */
export default function IndianPhoneField({
  id,
  value,
  onChange,
  name = "phone",
  inputRef,
  disabled,
  autoFocus,
  invalid,
  describedBy,
  className,
  inputClassName,
}: Props) {
  const frame = [styles.wrap, invalid ? styles.wrapInvalid : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={frame}>
      <span className={styles.prefix} aria-hidden="true">
        {INDIAN_PHONE_PREFIX}
      </span>
      <input
        id={id}
        ref={inputRef}
        name={name}
        className={inputClassName ? `${styles.input} ${inputClassName}` : styles.input}
        type="tel"
        inputMode="numeric"
        autoComplete="tel-national"
        placeholder="98765 43210"
        value={value}
        onChange={(e) => onChange(nationalDigits(e.target.value))}
        disabled={disabled}
        autoFocus={autoFocus}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        required
      />
    </div>
  );
}
