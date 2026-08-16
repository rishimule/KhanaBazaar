// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// `ApiError.detail` is `unknown` because this backend raises an object-shaped
// detail in 20+ places. Casting a caught error to `{ detail: string }` claims
// otherwise, and the object that comes back used to be pushed into React state
// and rendered as a JSX child — which React refuses, white-screening the whole
// operator dashboard on a duplicate status tap (seller UX audit BLOCKER #32).
//
// Targets the string annotation specifically: `{ detail?: unknown }` is the
// safe form, since TypeScript then forces the caller to narrow before use.
//
// Deliberately NOT anchored to TSAsExpression. The two forms are equally
// dangerous and this repo used both:
//     (e as { detail?: string }).detail          — the cast
//     .catch((e: { detail?: string }) => …)      — the parameter annotation
// Anchoring to the cast would have left the parameter form — the very form
// removed from admin/orders/[id]/page.tsx and ActiveOrdersWidget.tsx — free to
// come back. Matching the type literal itself covers both. A named `interface`
// with a `detail: string` member is a TSInterfaceBody, not a TSTypeLiteral, so
// legitimate declared types (e.g. FieldError) are unaffected.
//
// SCOPE OF PROTECTION — read before trusting this. A syntax selector cannot be
// a general defense. This reliably blocks a verbatim reintroduction of the
// deleted lines, which is its job. It does NOT catch `(e as any).detail`, a
// separately-declared named type, `as Record<string, string>`, or a nested
// literal. Closing those needs type-aware rules
// (@typescript-eslint/no-unsafe-member-access + no-explicit-any on these globs),
// which is a bigger change than this fix. Do not read a green lint as proof the
// class is gone.
const DETAIL_CAST_MESSAGE =
  "Do not type a caught error as `{ detail: string }`: the backend returns an object detail in 20+ places, and rendering that object crashes the page. Use apiErrorCode(err) or errorsKey(err) from @/lib/errors.";

// Two selectors, not one `:matches`: esquery resolves the union branch against
// the DIRECT child of TSTypeAnnotation, which for `string | null` is the
// TSUnionType — so a combined selector silently misses it. Probe-verified.
const NO_STRING_DETAIL_CAST = [
  {
    selector:
      "TSTypeLiteral > TSPropertySignature[key.name='detail'] > TSTypeAnnotation > TSStringKeyword",
    message: DETAIL_CAST_MESSAGE,
  },
  {
    selector:
      "TSTypeLiteral > TSPropertySignature[key.name='detail'] > TSTypeAnnotation > TSUnionType > TSStringKeyword",
    message: DETAIL_CAST_MESSAGE,
  },
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    // Every app surface. The crash sites for BLOCKER #32 spanned seller AND
    // admin, and review found the identical live pattern on the customer cart
    // and order pages — where it had already crashed for real, since
    // api/carts.py raises 400 with an object detail.
    //
    // MUST stay above the seller block below: flat config REPLACES
    // `no-restricted-syntax` rather than merging it, so for a seller file the
    // last matching block wins outright. Keeping this first means seller files
    // get the seller block's fuller list, and the empty-catch rules stay
    // seller-scoped as PR #272 intended.
    files: [
      "src/app/**/*.{ts,tsx}",
      "src/components/**/*.{ts,tsx}",
      "src/lib/**/*.{ts,tsx}",
    ],
    rules: {
      "no-restricted-syntax": ["error", ...NO_STRING_DETAIL_CAST],
    },
  },
  {
    // Seller surface only. A swallowed error here renders as "₹0", an empty
    // order list, or an absent suspension warning — states a shop owner reads
    // as the truth about their business. Track the error and show it (see
    // `components/LoadError.tsx` and `lib/useResource.ts`).
    //
    // Scoped deliberately: the customer and admin surfaces have their own
    // instances of this pattern, and widening the rule here would turn a
    // safety fix into an unrelated cleanup. Genuine no-op catches are allowed
    // as long as the block explains itself with a statement or a comment.
    files: [
      "src/app/(operator)/seller/**/*.{ts,tsx}",
      "src/components/seller/**/*.{ts,tsx}",
    ],
    rules: {
      "no-empty": ["error", { allowEmptyCatch: false }],
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "CallExpression[callee.property.name='catch'] > ArrowFunctionExpression[body.body.length=0]",
          message:
            "Do not swallow a seller-surface fetch error: an empty .catch() renders failure as a confident zero or empty list. Track the error and render <LoadError />.",
        },
        {
          selector:
            "CallExpression[callee.property.name='catch'] > FunctionExpression[body.body.length=0]",
          message:
            "Do not swallow a seller-surface fetch error: an empty .catch() renders failure as a confident zero or empty list. Track the error and render <LoadError />.",
        },
        // Repeated from the operator block above, which this block overrides
        // for seller files. Removing it here would silently un-ban the cast.
        ...NO_STRING_DETAIL_CAST,
      ],
    },
  },
]);

export default eslintConfig;
