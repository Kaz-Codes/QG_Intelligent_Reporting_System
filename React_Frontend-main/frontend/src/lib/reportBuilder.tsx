import type { ReactNode } from 'react'
import { StatusBadge } from '@/components/StatusBadge'
import { money, shortDate } from './format'
import { REPORT_TYPES, type ReportType, type ReportRow } from './api/reports'

/**
 * Column metadata for the report builder's table, column picker and file
 * exports — one definition per key the backend's normalised row can carry
 * (see app/reports/serializers.py ROW_KEYS), so a header only ever needs to
 * change in one place. A type's row has `null` for any key it doesn't apply
 * to; only the keys actually meaningful for a type appear in its column set.
 */

export interface ReportColumn {
  key: string
  label: string
  align?: 'right'
  render: (value: unknown, row: ReportRow) => ReactNode
  /** Plain-text form of the same value, for file export. */
  text: (value: unknown, row: ReportRow) => string
}

function dateText(v: unknown): string {
  return typeof v === 'string' && v ? shortDate(v) : ''
}
function dateRender(v: unknown): ReactNode {
  return typeof v === 'string' && v ? shortDate(v) : '—'
}
const statusCol: ReportColumn = {
  key: 'status', label: 'Status',
  render: (v) => (v ? <StatusBadge label={String(v)} /> : '—'),
  text: (v) => String(v ?? ''),
}
const dateCol: ReportColumn = { key: 'date', label: 'Date', render: dateRender, text: dateText }
const requiredDateCol: ReportColumn = { key: 'required_date', label: 'Required Date', render: dateRender, text: dateText }
// PPC/Store is a date in the source data, not a PPC-vs-Store category.
const ppcStoreCol: ReportColumn = { key: 'ppc_store', label: 'PPC / Store', render: dateRender, text: dateText }
const typeCol: ReportColumn = {
  key: 'type', label: 'Type',
  text: (v) => String(v ?? ''),
  render: (v) => REPORT_TYPES.find((t) => t.value === v)?.label ?? String(v ?? ''),
}

function plainCol(key: string, label: string, align?: 'right'): ReportColumn {
  return { key, label, align, render: (v) => String(v ?? '—'), text: (v) => String(v ?? '') }
}

// One shared 'value' column across all four types (so mixing e.g. Purchases
// + Inventory into one table still collapses to a single "Value" column
// instead of two), formatted per row by its own type — Inventory's value is
// a quantity, everything else is PKR.
const valueCol: ReportColumn = {
  key: 'value', label: 'Value', align: 'right',
  render: (v, row) => (row.type === 'inventory' ? Math.round(Number(v ?? 0)).toLocaleString() : money(Number(v ?? 0))),
  text: (v) => String(Math.round(Number(v ?? 0))),
}

export const COLUMNS_BY_TYPE: Record<ReportType, ReportColumn[]> = {
  purchases: [
    typeCol,
    plainCol('ref', 'Ref No'),
    plainCol('po_number', 'PO Number'),
    plainCol('bill_no', 'Bill No'),
    plainCol('item', 'Item'),
    plainCol('supplier', 'Supplier'),
    plainCol('branch', 'Branch'),
    plainCol('category', 'Category'),
    ppcStoreCol,
    plainCol('mop', 'Mode of Purchase'),
    plainCol('sourcing_officer', 'Sourcing Officer'),
    plainCol('quantity', 'Quantity', 'right'),
    valueCol,
    dateCol,
    requiredDateCol,
    statusCol,
  ],
  imports: [
    typeCol,
    plainCol('ref', 'Reference'),
    plainCol('supplier', 'Supplier'),
    plainCol('country', 'Country'),
    plainCol('branch', 'Branch'),
    plainCol('category', 'Category'),
    valueCol,
    plainCol('mode_of_shipment', 'Mode of Shipment'),
    statusCol,
    dateCol,
  ],
  inventory: [
    typeCol,
    plainCol('ref', 'Item Code'),
    plainCol('item', 'Item'),
    plainCol('branch', 'Branch'),
    plainCol('category', 'Category'),
    plainCol('specs', 'Specs'),
    valueCol,
    plainCol('stock_qty', 'Stock Qty', 'right'),
    plainCol('hold_qty', 'Hold Qty', 'right'),
    plainCol('reorder_level', 'Reorder Level', 'right'),
    statusCol,
    plainCol('reorder_status', 'Reorder Status'),
  ],
  logistics: [
    typeCol,
    plainCol('ref', 'Shipment Ref'),
    plainCol('customer', 'Customer'),
    plainCol('country', 'Country'),
    plainCol('pod', 'Port of Discharge'),
    statusCol,
    plainCol('stage', 'Stage'),
    plainCol('shipping_line', 'Shipping Line'),
    valueCol,
    plainCol('cost_per_kg', 'Cost / Kg', 'right'),
    dateCol,
  ],
}

/** Union of column defs across the given types, in a stable order, deduped
 * by key (shared keys like 'branch' collapse into a single column). */
export function unionColumns(types: ReportType[]): ReportColumn[] {
  const seen = new Set<string>()
  const out: ReportColumn[] = []
  for (const t of types) {
    for (const col of COLUMNS_BY_TYPE[t]) {
      if (seen.has(col.key)) continue
      seen.add(col.key)
      out.push(col)
    }
  }
  return out
}
