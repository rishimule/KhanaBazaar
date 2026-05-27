// Verifies all locale files expose identical key trees. Exit 1 on mismatch.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "messages");
const locales = ["en", "hi", "mr", "gu", "pa"];

function keyPaths(obj, prefix = "") {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    // Skip annotation/metadata keys (e.g. __translatorNote) — intentionally
    // asymmetric across locales, not translatable message keys.
    if (k.startsWith("__")) continue;
    const p = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) out.push(...keyPaths(v, p));
    else out.push(p);
  }
  return out.sort();
}

const sets = Object.fromEntries(
  locales.map((l) => [
    l,
    new Set(keyPaths(JSON.parse(readFileSync(join(dir, `${l}.json`), "utf8")))),
  ]),
);

const base = sets.en;
let failed = false;
for (const l of locales.filter((l) => l !== "en")) {
  const missing = [...base].filter((k) => !sets[l].has(k));
  const extra = [...sets[l]].filter((k) => !base.has(k));
  if (missing.length || extra.length) {
    failed = true;
    console.error(`\n[${l}] missing: ${missing.join(", ") || "—"}`);
    console.error(`[${l}] extra:   ${extra.join(", ") || "—"}`);
  }
}
if (failed) {
  console.error("\nMessage-key parity FAILED.");
  process.exit(1);
}
console.log("Message-key parity OK across", locales.join(", "));
