# QG-IRS — Qadri Group Intelligent Reporting System

An internal **AI Supply Chain Intelligence Platform** for **Qadri Group**, a
manufacturing company. QG-IRS turns supply-chain data — purchases, inventory,
imports, logistics — into a fast, executive-friendly reporting workspace:
dashboards, custom reports, and a natural-language assistant, all in one place.

It runs on the company's own network (no cloud), and is used by everyone from
directors to data-entry clerks — so it's built to be simple to read yet
powerful underneath, and it's presented to top management.

> **Status:** active development. The full UI is built and running on realistic
> sample data. The production database/API is a separate teammate's workstream
> and is swapped in later without changing the pages (see
> [Data & the backend](#data--the-backend)).

<p align="center">
  <img src="docs/screenshots/login.png" alt="QG-IRS login screen" width="80%">
</p>

---

## Screens

| Executive Dashboard | Dark mode |
| --- | --- |
| ![Dashboard](docs/screenshots/dashboard-light.png) | ![Dashboard dark](docs/screenshots/dashboard-dark.png) |

| Imports | QadriBot assistant |
| --- | --- |
| ![Imports](docs/screenshots/imports.png) | ![Assistant](docs/screenshots/assistant.png) |

---

## What's inside

Ten sections, reachable from the sidebar:

| Section | What it shows |
| --- | --- |
| **Dashboard** | Executive overview — headline KPIs, purchase-value trend, supplier performance, status split, aging, and an attention feed. |
| **Purchases** | Purchase orders by supplier / branch / category with KPIs, charts, and a searchable table. |
| **Inventory** | Current stock levels, out-of-stock / below-reorder risk, and stock-runway insights. |
| **Imports** | Import shipments, values, and customs-clearance status. |
| **Imports Status** | Consignment tracking with a **six-step** data-entry wizard (Consignment, Finance, Shipping, Payments, Status & Remarks, Clearance — the old Landed Cost step was dropped since accounts, not this system, finalise ELC/ALC). Step 1 carries an **Incoterm** field alongside requisition/required dates, and each item line captures **weight & dimensions** (net/gross kg, L/W/H) — expected before an FOB consignment is handed to trucking, since the truck load-out and freight rate depend on them. Clearance tracks **Container Detention** (PKR) alongside demurrage. The list is a sortable, **paginated** sheet (10/page) keyed off the LC/DP **instrument reference**, with the **Payment** column second (right after the ID) and an **ETD date-range** filter; it scrolls horizontally on narrow desktops. Export Excel / Export PDF produce a real `.xlsx` (frozen header, autofilter, auto-fit columns) and a real landscape `.pdf` over the filtered set, via the shared `src/lib/listExport.ts`. See [Data & the backend](#data--the-backend). |
| **Logistics Status** | Export / local order tracking with a **five-step** data-entry wizard: Order Details, **Packing**, Shipping, Expenditures, Status. Step 1 now carries a **Department** (Cement / Sugar / General — merges with order type into the list's "Order Type" column, e.g. "Cement Export") and the **MO / batch system**: entering an MO number that already exists in the system auto-assigns this order as the next batch under it (Batch 1, 2, …), with a user-renameable label. Items are simplified — Job #, item detail, quantity, a real **Unit Weight** input, a derived **Net Weight**, and **Planned/Actual RFD dates** with a full per-item change-audit trail (who/when/old→new), surfaced as system remarks. Packing's per-package allocation rows now carry a **Job # badge** ("No job #" when the item hasn't been assigned one yet) and support **cross-batch allocation**: a package on Batch 2 can allocate quantity from an item that physically belongs to a sibling Batch 1 order under the same MO — items are shared by reference, never copied — plus a footer totalling net/gross weight across every package. Shipping's container numbers are enforced **unique** (case/space-insensitive) both within an order and across every other order in the system, with an inline error and Next blocked on a duplicate. Expenditures gains **Container Detention**. Status adds a derived **Marketing Delay**, the merged remarks feed (admin-gated edits), and the one-way **Send to Trucking** handoff with a live read-through once a Trucking job exists. The **system ID is the MO number itself** (Batch 1) or `{moNo}-B{batchNo}` (Batch 2+), never a random id — orders with no MO fall back to a sequential `LOG-{year}-####`. An **Orders \| Service Jobs** tab sits above the list: Orders keeps the full MO/batch table (MO #, Order Type, Job #, Customer, Batch # with an MO-group accent, Items, Packages, Net/Gross Weight, Works, Incoterm, an **Arrival delay** pill, and an **Actual RFD** column — falling back to a muted "(planned)" reading until the real date lands), with a gate-out date-range filter, sortable headers, pagination (10/page), and horizontal scroll; **Service Jobs** unifies the read-only **Import FOB** feed (handed over from Imports, opens the source consignment) with owned **Customer Rework** jobs (goods a customer sends in for rework, with a lightweight logistics-entered create form) — no full order wizard, just one panel. Export Excel / PDF produce real `.xlsx`/`.pdf` files over the filtered Orders set (shared `src/lib/listExport.ts`). See [Data & the backend](#data--the-backend). |
| **Trucking Status** | Vehicle-movement jobs (Intrafactory / Outbound / Inbound) with a four-step data-entry wizard — Freight & Payment now also tracks **Detention** (PKR). Builty tracking was removed. The Vehicles step gains two independent per-vehicle checklists: a **package checklist** for jobs taken from a Logistics order with packages, and an **import-consignment checklist** for Inbound jobs (two or more import shipments can legitimately ride one truck; checking one pre-fills its gross weight from the source consignment, editable per vehicle, and the vehicle-summary footer rolls up consignment counts and import weight) — both warn rather than block on double-assignment. The list is split into **two tables**: an **Open Requests** table of live, never-copied handoffs from Logistics (once **Send to Trucking** is checked), Imports (FOB past Under Production) and Export — tagged by source, each with Open + **Take Action** — sitting above a **Trucking Jobs** table of the module's own manual + taken jobs (Open + Edit, with a **Delay** column against ETA-to-works). **Take Action** converts a Logistics/Import-FOB request into an independent job, snapshotting the source's items/packages, pre-filling the wizard, and permanently excluding that source from further live derivation (Export stays always-live with no accept step). Both tables share one filter bar (movement, source, execution-date range) and scroll horizontally on narrow desktops; the Jobs table has **sortable headers** and **pagination** (10/page), and the Open Requests table shows a Transporter column. Export Excel / PDF produce real `.xlsx`/`.pdf` files (both tables combined) via the shared `src/lib/listExport.ts`. See [Data & the backend](#data--the-backend). |
| **Logistics** | Export shipments, packing, transport, and documentation. |
| **Reports** | A custom report builder — pick a source, columns, and filters, then export. |
| **Assistant (QadriBot)** | Ask about the data in plain language and get an answer, table, or chart back. |

Across every page:

- **Light & dark mode** — toggle in the sidebar, remembered between visits.
- **Role-based access** — four roles gate *actions* (see [Roles](#roles--permissions)).
- **Themed, animated backgrounds** — each section has a subtle backdrop of
  drifting, subject-related icons (planes & ships on Imports, boxes & forklifts
  on Inventory, …) over soft accent-tinted glows.
- **Motion throughout** — hover lift on cards, fade-in page and tab
  transitions, animated filter dropdowns.

---

## Tech stack

- **[Vite](https://vite.dev/) + [React 19](https://react.dev/) + TypeScript**
- **[Tailwind CSS v4](https://tailwindcss.com/)** with shadcn-style UI primitives
- **[Recharts](https://recharts.org/)** for charts
- **[React Router](https://reactrouter.com/)** for navigation
- **[lucide-react](https://lucide.dev/)** for icons
- **[react-hook-form](https://react-hook-form.com/) + [zod](https://zod.dev/)**
  for multi-step forms
- **[SheetJS](https://sheetjs.com/) (xlsx) + [jsPDF](https://github.com/parallax/jsPDF) + jspdf-autotable**
  for the shared list Excel/PDF export (`src/lib/listExport.ts`)
- **[TanStack Query](https://tanstack.com/query)** (ready for when the real API lands)

---

## Run it

The app is currently **frontend-only** — all data is mocked in the browser, so
there's nothing else to start.

```bash
cd frontend
npm install      # first time only
npm run dev
```

Open the URL Vite prints (**http://localhost:5173**) and sign in with one of the
demo accounts below.

Other scripts:

```bash
npm run build    # production bundle
npm run preview  # serve the production build locally
npm run lint     # oxlint
```

### Demo credentials

| Username | Password | Role |
| --- | --- | --- |
| `admin` | `admin123` | admin |
| `manager` | `admin123` | manager |
| `entry` | `admin123` | entry |
| `viewer` | `admin123` | viewer |

> These are a **frontend-only development gate**, not real security — anyone can
> read them from the shipped JS. They exist only so the UI can be built and
> reviewed before the real login API exists. See
> [Data & the backend](#data--the-backend).

---

## Project structure

```
frontend/
├── src/
│   ├── pages/                 one file per report/dashboard tab
│   │   └── logistics/         Logistics' four sub-views
│   ├── features/
│   │   ├── auth/              login, auth context, protected routes
│   │   ├── importsStatus/     consignment tracking + entry wizard
│   │   ├── logisticsStatus/   order tracking + entry wizard (scaffold only)
│   │   └── truckingStatus/    vehicle-movement tracking + entry wizard
│   ├── components/            shared UI (cards, filters, charts, layout, …)
│   │   └── charts/            themed Recharts wrappers
│   ├── lib/
│   │   ├── mockData/          sample data — the swap-for-real-API boundary
│   │   ├── mockAuth.ts        temporary login stub
│   │   ├── pages.ts           sidebar / route registry (single source of truth)
│   │   └── roleAccess.ts      roles + the can() permission helper
│   ├── theme/                 design tokens + light/dark palettes
│   └── index.css              CSS variables, Tailwind theme, keyframes
docs/screenshots/              images used in this README
```

To **add or reorder a tab**, edit `src/lib/pages.ts` (sidebar) and
`src/App.tsx` (routes) — nothing else needs to know.

---

## Roles & permissions

Four roles, defined in `src/lib/roleAccess.ts`:

| Role | Enter | Edit existing | Reports | Manage users | Manage masters |
| --- | --- | --- | --- | --- | --- |
| admin | yes | yes | yes | yes | yes |
| manager | yes | yes | yes | no | yes |
| entry | yes | own drafts only | yes | no | inline-create only |
| viewer | no | no | read-only | no | no |

Every role can **see every page** and all financial values — the matrix only
restricts *actions* (create / edit / manage). Components ask one question rather
than checking role strings inline:

```ts
import { can } from '@/lib/roleAccess'

if (can(user, 'enter')) {
  // show the "New" button
}
```

---

## Design system

- **Colors, fonts, and status meanings live in one place** —
  `src/theme/tokens.ts` (JS values, for charts) and `src/index.css` (CSS
  variables, flipped by the `.dark` class). A rebrand is a one-file change;
  **keep the two in sync** if you touch the palette.
- **Navy** is structure, **gold** is the brand accent, an **indigo→violet**
  gradient is the one signature highlight, and **red / amber / green** are used
  *only* for status (risk / watch / healthy), never decoration.
- **All charts go through `src/components/charts/`** so they stay consistent and
  theme-aware in both light and dark mode.

---

## Data & the backend

The frontend never talks to a database or does calculations itself. Today every
page reads from **mock modules in `src/lib/mockData/`** that return realistic
sample data. When the production API (a separate teammate's workstream) is
ready, those modules — and `src/lib/mockAuth.ts` — are swapped for real API
calls. **The pages don't change**: same data shapes in, same UI out.

This keeps the two workstreams cleanly separated and lets the UI be built,
reviewed, and demoed now without waiting on the backend.

**Status colours:** every status pill/tag/badge across Imports Status,
Logistics Status and Trucking Status resolves its colour through
`statusColors()` in `src/theme/tokens.ts`, keyed off the real CSS custom
properties defined in `src/index.css` (`--color-risk` / `--color-watch` /
`--color-healthy` / `--color-info`, each with a matching `-bg`). The Imports
Status module's local atoms previously referenced a different, nonexistent
set of variable names (`--color-warning`, `--color-danger`, etc.) — nothing
crashed, but every pill/tag/dot rendered colourless. Fixed by pointing them
at the real tokens; the mapping (danger→risk, warning→watch, success→healthy,
info→info) is documented at the top of `src/features/importsStatus/components/atoms.tsx`.

**Item edits persisting on save:** `updateConsignment()` in
`src/lib/importsStatusData.ts` previously patched only the consignment's
header fields and silently dropped every per-item edit — so item weights
entered in the wizard never reached the flat `ConsignmentRow` the list and
the cross-module trucking hand-off read, and an FOB consignment always looked
weightless to Trucking. Fixed by rebuilding `row.items` from the saved draft
(and re-deriving `requisitionSummary` from it) whenever the draft carries
items, so weight/dimension and any other line edits actually survive the save.

---

## Working in this repo

Two of us build the React app side by side:

- **Report & dashboard pages** (the eight sections above) — `src/pages/`,
  `src/features/auth/`, shared `src/components/`.
- **Data-entry pages** (e.g. the Imports Status wizard) —
  `src/features/importsStatus/`.

To keep merges painless, the shared "registry" files are **additive by design**:
adding a page is a one-line addition to `src/lib/pages.ts` and a route in
`src/App.tsx`, not a rewrite of shared logic. Pull before touching those files.

**Forms:** anything beyond a couple of fields uses **react-hook-form + zod** —
follow the pattern in `src/features/importsStatus/` (one zod schema per step,
one `useForm`, validate the current step on “Next”) rather than hand-rolling
`useState`.

**Nested routes:** a feature with more than one screen nests its routes under a
single parent path (see `/imports-status` in `src/App.tsx`) rather than adding
loose top-level routes.
