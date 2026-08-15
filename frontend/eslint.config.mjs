// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

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
      ],
    },
  },
]);

export default eslintConfig;
