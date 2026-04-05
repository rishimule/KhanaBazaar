# Architectural Patterns & Conventions

## Backend: Dependency Injection Chain (FastAPI `Depends`)

All auth and DB access flows through composable FastAPI dependencies defined in `backend/app/src/app/core/security.py`.

**Chain:** `HTTPBearer` -> `verify_firebase_token` -> `get_current_user` -> role guards (`get_current_seller`, `get_current_admin`).

- `verify_firebase_token` (`security.py:27`) decodes the Firebase JWT from the `Authorization` header.
- `get_current_user` (`security.py:43`) looks up the DB user by `firebase_uid`.
- `get_current_seller` (`security.py:64`) and `get_current_admin` (`security.py:73`) enforce RBAC by checking `user.role`.
- `get_db_session` (`db/session.py:14`) yields an `AsyncSession` per request.

Endpoints declare their access level by choosing which dependency to inject:
- **Public:** only `Depends(get_db_session)` — e.g., `catalog.py:14`, `stores.py:19`
- **Seller:** `Depends(get_current_seller)` — e.g., `stores.py:29`
- **Admin:** `Depends(get_current_admin)` — e.g., `catalog.py:19`

## Backend: SQLModel Three-Tier Model Hierarchy

All database models follow a consistent inheritance pattern rooted in `backend/app/src/app/models/base.py`:

1. **`BaseSchema`** (`base.py:13`) — provides `id`, `created_at`, `updated_at` with timezone-aware UTC timestamps.
2. **`*Base` mixin** (e.g., `UserBase` at `base.py:25`, `ItemBase` at `base.py:35`) — defines domain fields without `table=True`.
3. **Table model** (e.g., `User` at `base.py:32`, `Item` at `base.py:40`) — combines `BaseSchema` + mixin with `table=True`.

This pattern separates request/response schemas from DB table definitions while sharing field declarations. Catalog (`catalog.py`) and Store (`store.py`) models follow the same structure, always inheriting from `BaseSchema`.

## Backend: Router Registration Pattern

Routers are organized one-file-per-domain in `backend/app/src/app/api/`:
- Each file defines `router = APIRouter()` and exports it.
- `api/__init__.py:1-9` aggregates all routers onto a single `api_router` with prefix/tag pairs.
- `__init__.py:17` (app root) mounts `api_router` under `settings.API_V1_STR` (`/api/v1`).

To add a new domain: create `api/new_domain.py` with `router = APIRouter()`, then register it in `api/__init__.py`.

## Backend: Test Auth Override Pattern

Tests bypass Firebase entirely using FastAPI's `dependency_overrides` mechanism:

- `tests/conftest.py:40` overrides `get_db_session` globally to use a separate `khanabazaar_test` Postgres database (not SQLite).
- `tests/conftest.py:27-34` drops/recreates all tables per test function for isolation.
- Per-test-file fixtures (e.g., `test_stores.py:18-39`) override role dependencies (`get_current_admin`, `get_current_seller`) with mock `User` objects.
- Fixtures yield and then pop overrides to avoid cross-test contamination.

This pattern allows testing protected endpoints without a running Firebase instance.

## Frontend: CSS Modules + Design Tokens (No Tailwind)

Styling uses CSS Modules for scoping and CSS custom properties for theming:

- **Design tokens** defined in `frontend/src/styles/design-tokens.css` — colors, typography, spacing, shadows, z-index, etc.
- **Component styles** co-located as `*.module.css` files (e.g., `ProductCard.module.css`, `DashboardLayout.module.css`).
- **Global utility classes** (e.g., `btn`, `btn-primary`, `btn-outline`) defined in `frontend/src/app/globals.css`.
- Components import their module: `import styles from "./Component.module.css"` and apply via `className={styles.foo}`.

## Frontend: State Management — Context + localStorage Cart

Cart state uses a two-layer architecture:

1. **Persistence layer** (`frontend/src/lib/cart.ts`) — pure functions that read/write carts to `localStorage` under key `kb_carts`. Each store gets its own cart (multi-store model). A `kb_session_id` (UUID) identifies the guest.
2. **React layer** (`frontend/src/lib/CartContext.tsx`) — wraps `cart.ts` in a React Context with `useState`. `CartProvider` (`CartContext.tsx:48`) is mounted in `app/layout.tsx:52`. Components access cart via `useCart()` hook (`CartContext.tsx:112`).

This separation means cart logic is testable without React and SSR-safe (all `localStorage` access is guarded by `typeof window` checks).

## Frontend: Shared Dashboard Layout Pattern

Admin and Seller portals reuse a single `DashboardLayout` component (`frontend/src/components/DashboardLayout.tsx`):

- Accepts `role`, `roleName`, `title`, and `navItems` props.
- Provides sidebar navigation, mobile toggle, and content area.
- Each portal has its own Next.js layout file (`app/seller/layout.tsx`, `app/admin/layout.tsx`) that configures nav items and derives the page title from `usePathname()`.

## Frontend: TypeScript Types Mirror Backend Models

`frontend/src/types/index.ts` defines interfaces that exactly mirror backend SQLModel schemas:
- `BaseSchema` matches the `id`, `created_at`, `updated_at` fields.
- Domain types (`User`, `Category`, `MasterProduct`, `Store`, `StoreInventory`) match their Python counterparts.
- Frontend-only types (`CartItem`, `Cart`, `InventoryWithProduct`) extend the pattern for client-side needs.

When backend models change, these types must be updated manually to stay in sync.

## Frontend: API Client Pattern

`frontend/src/lib/api.ts` provides typed `get`, `post`, `put`, `del` wrappers around `fetch`:
- Base URL from `NEXT_PUBLIC_API_URL` env var (defaults to `http://localhost:8000`).
- All responses pass through `handleResponse` which throws a structured `ApiError` on non-ok status.
- Callers use generics: `get<Store[]>("/api/v1/stores/")`.
