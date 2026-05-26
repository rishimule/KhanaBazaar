# Khana Bazaar — Design System

The visual language for the Khana Bazaar frontend: a warm, food-themed,
flat-and-dense commerce UI. **Saffron** is the brand chrome, **turmeric/golden
saffron** is the call-to-action, surfaces are flat white with 1px hairlines, and
type is Poppins everywhere.

This document describes *intent and rules*. The source of truth is
`frontend/src/styles/design-tokens.css` (the tokens) and
`frontend/src/app/globals.css` (the global element + utility styles). When they
disagree with this doc, the CSS wins — update this doc.

---

## 1. Architecture

```
frontend/src/
  styles/design-tokens.css   # :root CSS custom properties — the ONLY source of raw values
  app/globals.css            # reset, element defaults, utility classes (.btn, .badge, .pill, .price, .input)
  components/*.module.css    # component-scoped CSS Modules
  app/**/*.module.css        # page-scoped CSS Modules
```

Three layering rules, in order:

1. **Tokens hold every raw value.** Colors, spacing, radii, shadows, type sizes,
   z-index, breakpoints. Components reference `var(--token)` — never hardcode a
   hex, px gap, or shadow.
2. **`globals.css` owns shared primitives** as global classes: `.btn*`,
   `.badge*`, `.pill*`, `.price*`, form inputs, `.container`, `.truncate`,
   `.sr-only`, animation helpers.
3. **Everything else is a CSS Module** (`*.module.css`, ~96 of them). Component
   styling is scoped; class names are local. No global component CSS, no inline
   style objects for anything a token covers.

**Never add Tailwind.** No utility-class frameworks. CSS Modules + tokens only.

Font is wired in the route-group layouts (`app/(operator)/layout.tsx`,
`app/(customer)/[locale]/layout.tsx`) via `next/font/google` Poppins, exposed as
the `--font-poppins` CSS variable on `<html>`. `--font-family-sans` consumes it
with a system-font fallback chain.

---

## 2. Color

### Brand & action

| Role | Token | Value | Use |
|------|-------|-------|-----|
| Brand chrome | `--color-primary-1` | `#B8470F` saffron deep | wordmark, nav, links, active state |
| Primary CTA bg | `--color-btn-primary-bg` | `#F18A1F` golden saffron | primary buttons |
| Primary CTA hover | `--color-btn-primary-hover` | `#D9731B` | button hover |
| Inline link / accent | `--color-link` | `#E8611A` saffron base | inline links, accents |

Two ramps back these: **Saffron** (`--saffron-*`, brand side) and **Turmeric**
(`--turmeric-*`, golden action side).

> **Legacy aliases:** earlier the palette was cobalt navy + teal ("Energy Blue",
> "Flow Teal"). Those token names still exist but are **remapped** to saffron/
> turmeric so untouched components inherit the warm system. Don't reintroduce
> `--energy-blue-*` / `--flow-teal-*` in new code — use the saffron/turmeric or
> semantic tokens. Same for the `--color-primary-50..900` / `--color-accent-*` /
> `--color-neutral-*` numeric ramps: kept for back-compat, mapped to warm.

### Food-themed accents

Each maps to a semantic job — use the *job*, not the raw color name, when one exists:

| Accent | Base token | Job |
|--------|-----------|-----|
| Tomato Red | `--tomato-red-base-4` `#ec4143` | sale / urgency / destructive (`--color-sale`, `--color-error`) |
| Mandarin Orange | `--mandarin-orange-base-4` `#ff5026` | warmth / hot / warning (`--color-warning`) |
| Durian Yellow | `--durian-yellow-base-4` `#ffd600` | member / EBT / stars |
| Jade Green | `--jade-green-dark-1` `#018260` | savings / success (`--color-savings`, `--color-success`) |
| Chive Green | `--chive-green-base-4` `#2da34f` | fresh produce / in-stock / local |
| Dragonfruit Pink | `--dragonfruit-pink-base-4` `#f43c7e` | wishlist / beauty |
| Eggplant Purple | `--eggplant-purple-base-4` `#9654ff` | premium / wellness / limited |

### Neutrals — cool-tinted, never warm

The `--shade-cool-*` ramp is the grayscale. It is deliberately **cool-tinted**
to sit against the warm brand. Don't mix in warm grays.

| Token | Use |
|-------|-----|
| `--shade-cool-dark-7` `#07101a` | headings (`--color-text-strong`) |
| `--shade-cool-base-7` `#52667d` | body text (`--color-text`) |
| `--shade-cool-base-5` `#758296` | secondary metadata (`--color-text-muted`) |
| `--shade-cool-base-4` `#9299ae` | disabled / strikethrough (`--color-text-disabled`) |
| `--shade-cool-light-6` `#d3daeb` | input borders (`--color-input-border`) |
| `--shade-cool-light-2` `#eef2fb` | search bg, selected sidebar (`--color-surface-tint`) |
| `--shade-cool-light-1` `#f6f9fc` | page tint (`--color-page`) |
| `--hairline` `#eaeaea` | the 1px workhorse divider (`--color-divider`) |

### Semantic aliases — prefer these in components

Use role tokens, not raw ramps, so a future re-theme stays one-file:

```
--color-text-strong / --color-text / --color-text-muted / --color-text-disabled
--color-surface (white) / --color-surface-tint / --color-page
--color-divider / --color-input-border
--color-sale / --color-savings / --color-success / --color-warning / --color-error
```

### Gradients

`--gradient-brand-sweep` (saffron sweep), `--gradient-sale-sweep` (tomato→pink),
`--gradient-member-sweep` (gold→orange). Used sparingly — flat is the default.

---

## 3. Typography

**Poppins** for everything (display + body + UI). No serif, no second family
except `--font-family-mono` for code-ish numerics.

- **Display scale** (`--display-5xl` 72px … `--display-sm` 20px): weight **500
  medium**, negative letter-spacing (tracking tokens paired per size).
- **Body scale** (`--body-2xl` 24px … `--body-3xs` 11px): weight **400**.
- **Weights:** `--weight-regular` 400 · `--weight-medium` 500 ·
  `--weight-semibold` 600 · `--weight-bold` 700 · `--weight-extra` 800.

Element defaults are set in `globals.css`: `h1`→`--display-2xl`, `h2`→
`--display-xl`, `h3`→`--display-lg`, `h4`→`--display-sm`, `h5`/`h6` shift to
semibold body sizes.

**Line-height gotcha:** `--lh-display` is **1.2, not 1.0**, so the top matras of
Devanagari / Gujarati / Gurmukhi (hi, mr, gu, pa locales) clear the line box. At
1.0 they sit above it and clip. Don't tighten display line-height below 1.2.

**Prices** always use `.price` — `font-variant-numeric: tabular-nums`, semibold.
Variants: `.price--sale` (tomato), `.price--member` (jade), `.price--strike`
(struck, muted).

---

## 4. Spacing, radii, shadows

- **Spacing:** 8px base scale, 4px allowed. `--space-1` 4px … `--space-24` 96px.
  Use the scale tokens; don't invent gaps.
- **Radii:** `--radius-card` 10px · `--radius-modal` 12px · `--radius-sheet` 16px
  · `--radius-pill` 100px · `--radius-circle` 50% · `--radius-badge` 4px.
- **Shadows — flat by default.** The system is intentionally flat. Shadows are
  *transient only*: `--shadow-card-hover` (on hover), `--shadow-search` (dropdown),
  `--shadow-modal`, `--shadow-sticky-bar`, `--shadow-toast`. At rest, surfaces
  use a 1px hairline border instead of a shadow. Legacy `--shadow-xs..2xl` and
  the `--shadow-glow-*` tokens collapse to subtle/none — don't add resting glows.

---

## 5. Motion

- **Easing:** `--ease-default` / `--ease-in-out` (the standard), `--ease-out`
  (enters), `--ease-bounce` (playful, rare).
- **Durations:** `--duration-fast` 150ms (hover/press) · `--duration-normal`
  200ms · `--duration-slow` 300ms (entrances) · `--duration-slower` 500ms.
- **Keyframe helpers** in globals: `.animate-fade-in`, `.animate-fade-in-up`,
  `.animate-slide-in-right` (all 300ms ease-out).
- **Press feedback:** `.btn:active { transform: scale(0.97) }`. Cards lift
  `translateY(-2px)` + hover shadow on hover (see ProductCard).

Keep motion short and functional; this is a dense commerce UI, not a showcase.

---

## 6. Components (global primitives)

Defined in `globals.css`, used everywhere via plain class names.

### Buttons — `.btn` + variant

| Variant | Look |
|---------|------|
| `.btn-primary` / `.btn-accent` | golden-saffron fill, white text, 10px radius, 14×24 pad |
| `.btn-secondary` / `.btn-outline` | white, saffron text, hairline border → saffron on hover, **pill** radius |
| `.btn-tertiary` / `.btn-ghost` | transparent, saffron text, tinted hover bg |
| `.btn-destructive` / `.btn-danger` | transparent, tomato text, tomato-tint hover |
| `.btn-pill` | radius modifier → pill |

Disabled (`:disabled` / `[aria-disabled="true"]`): light-gray fill, muted text,
no transform.

### Badges — `.badge` + variant

Uppercase micro-pills, `--body-2xs`, semibold, 4px radius. Variants map to the
food accents: `--sale`, `--new`, `--hot`, `--ebt`, `--member`, `--limited`,
`--local`, `--instock`, `--success`, `--warning`, `--neutral`.

### Pills / filter chips — `.pill`, `.pill--active`

White hairline pill → saffron border/text on hover; active = saffron fill.

### Form inputs

Element selectors wrapped in `:where(...)` so specificity stays **0** and any
component class can override without `!important`. Flat white, hairline border,
10px radius, 14×16 pad. Focus = saffron border + 2px saffron-tint ring
(`rgba(184,71,15,0.12)`). Error = tomato border (`.input--error` /
`[aria-invalid="true"]`).

### Layout utilities

`.container` (max `--container-2xl` 1600px, responsive inline padding),
`.truncate`, `.sr-only`. Global `:focus-visible` = 2px saffron outline, 2px
offset — keep it; it's the accessibility default.

---

## 7. Layout & responsive

- **Containers:** `--container-xs` 480 … `--container-3xl` 1920. Default page
  width caps at `--container-2xl` 1600.
- **Breakpoints:** `--bp-sm` 480 · `--bp-md` 768 · `--bp-lg` 1024 · `--bp-xl`
  1280 · `--bp-2xl` 1440 · `--bp-3xl` 1920. Mobile breakpoint for the customer
  shell is **1023px** (`max-width: 1023px` switches to mobile nav + tab bar).
- **Fixed chrome:** `--nav-height` 64px (desktop), `--nav-height-mobile` 104px.
  `--sidebar-width` 200px, `--cart-rail-width` 360px. Body gets
  `padding-top: var(--nav-height)`; `.kb-customer-root` swaps to mobile nav
  height + a bottom tab-bar safe-area inset under 1023px.
- **Z-index** is a scale, not magic numbers: `--z-dropdown` 100 · `--z-sticky`
  200 · `--z-overlay` 300 · `--z-modal` 400 · `--z-popover` 500 · `--z-toast`
  600 · `--z-max` 9999.

---

## 8. Imagery

Product images are remote (LoremFlickr in dev seed; per-category themed pools).
Rendered via raw `<img referrerPolicy="no-referrer">` to avoid leaking browse
paths to the CDN, with a **category-emoji glyph fallback** on load failure.
Product cards use a square **1:1** image with badges absolute top-left and
wishlist top-right. No local image files in `frontend/public/`.

---

## 9. Conventions for new UI

1. **Reach for a token first.** New color/spacing/shadow → does a token exist?
   If a *semantic* token fits (`--color-text-muted`), use it over the raw ramp.
2. **Reuse global primitives** (`.btn`, `.badge`, `.pill`, `.price`, inputs)
   before writing component CSS.
3. **One CSS Module per component**, imported as `styles`. Scope class names
   locally; don't leak global classes from a module.
4. **Flat at rest, shadow on interaction.** Hairline borders separate surfaces;
   shadows appear only on hover/overlay/sticky/toast.
5. **Test all five locales** for any text-bearing component — en, hi, mr, gu, pa.
   Watch display line-height (matra clipping) and truncation in longer scripts.
6. **No Tailwind, no inline hardcoded values, no new font family.**
7. If you need a value no token provides, **add the token** to
   `design-tokens.css` (and, if shared, the primitive to `globals.css`) — don't
   one-off it in a module.

---

*Tokens: `frontend/src/styles/design-tokens.css` · Globals:
`frontend/src/app/globals.css` · Component styles:
`frontend/src/**/*.module.css`.*
