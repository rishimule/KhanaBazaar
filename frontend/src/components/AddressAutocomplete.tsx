"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  autocomplete,
  newSessionToken,
  placeDetails,
  type GeoPlace,
  type GeoPrediction,
} from "@/lib/geo";

import styles from "./AddressAutocomplete.module.css";

export interface AddressAutocompleteProps {
  initialValue?: string;
  placeholder?: string;
  /** Called once the user picks a suggestion AND the place-details lookup
   *  resolves with lat/lng + components. */
  onPlace: (place: GeoPlace) => void;
  disabled?: boolean;
}

export function AddressAutocomplete({
  initialValue = "",
  placeholder = "Search for your address",
  onPlace,
  disabled,
}: AddressAutocompleteProps) {
  const [query, setQuery] = useState(initialValue);
  const [predictions, setPredictions] = useState<GeoPrediction[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionTokenRef = useRef<string>(newSessionToken());
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    if (query.length < 3) {
      setPredictions([]);
      setOpen(false);
      return;
    }
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(async () => {
      try {
        const r = await autocomplete(query, sessionTokenRef.current);
        setPredictions(r.predictions);
        setOpen(r.predictions.length > 0);
        setError(null);
      } catch {
        setError("Suggestions unavailable, type address manually");
        setPredictions([]);
        setOpen(false);
      }
    }, 250);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [query]);

  const pick = useCallback(
    async (p: GeoPrediction) => {
      try {
        const place = await placeDetails(p.place_id, sessionTokenRef.current);
        onPlace(place);
        setQuery(place.formatted_address);
        setOpen(false);
        // Google billing: regenerate session token after place-details so the
        // next address-entry session starts fresh.
        sessionTokenRef.current = newSessionToken();
      } catch {
        setError("Could not load address details");
      }
    },
    [onPlace],
  );

  return (
    <div className={styles.wrapper}>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => predictions.length > 0 && setOpen(true)}
        placeholder={placeholder}
        disabled={disabled}
        className={styles.input}
        autoComplete="off"
      />
      {error && <span className={styles.error}>{error}</span>}
      {open && predictions.length > 0 && (
        <ul className={styles.dropdown} role="listbox">
          {predictions.map((p) => (
            <li
              key={p.place_id}
              className={styles.option}
              role="option"
              aria-selected={false}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => void pick(p)}
            >
              {p.description}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
