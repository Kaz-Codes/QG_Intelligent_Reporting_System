# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Trucking wizard notes

- **Transporters** (`src/lib/mastersTransporters.ts`) is a mock, in-memory
  master used by the Masters screen's "Transporters" tab and the trucking
  wizard's Transporter Name datalist. There is no backend transporter master
  yet; additions don't persist across a reload. Swap it for
  `listMasters('transporter')` / `createMaster('transporter')` once the
  backend has a real registry entry.
- **Shipment reference / IDM** on a trucking job is optional at submit —
  it is not required by `truckingSubmitSchema`.
- **Vehicle Type** (Step 2) and **Shifting Type** (Step 1, now including
  "Emergency") are fixed dropdowns (`VEHICLE_TYPES` / `SHIFTING_TYPES` in
  `features/truckingStatus/schema.ts`), not free text.
- The wizard's step navigation only re-saves when there are unsaved edits —
  clicking a step with no dirty state jumps straight there; a dirty step
  prompts to save-and-move or move-without-saving.
