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
function dateCol(key: string, label: string): ReportColumn {
  return { key, label, render: dateRender, text: dateText }
}
const statusCol: ReportColumn = {
  key: 'status', label: 'Status',
  render: (v) => (v ? <StatusBadge label={String(v)} /> : '—'),
  text: (v) => String(v ?? ''),
}
const typeCol: ReportColumn = {
  key: 'type', label: 'Type',
  text: (v) => String(v ?? ''),
  render: (v) => REPORT_TYPES.find((t) => t.value === v)?.label ?? String(v ?? ''),
}

function plainCol(key: string, label: string, align?: 'right'): ReportColumn {
  return { key, label, align, render: (v) => String(v ?? '—'), text: (v) => String(v ?? '') }
}

// A plain number, not currency — foreign unit prices, exchange rates and
// weights don't carry a fixed PKR symbol the way `money()` assumes.
function numCol(key: string, label: string, decimals = 2): ReportColumn {
  const fmt = (v: unknown) => (v === null || v === undefined || v === '' ? null : Number(v))
  return {
    key, label, align: 'right',
    render: (v) => { const n = fmt(v); return n === null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: decimals }) },
    text: (v) => { const n = fmt(v); return n === null ? '' : String(n) },
  }
}

// A PKR figure that IS meaningful on its own row (unlike the shared `value`
// column below) — ELC/ALC and logistics' individual cost lines.
function moneyCol(key: string, label: string): ReportColumn {
  return {
    key, label, align: 'right',
    render: (v) => (v === null || v === undefined || v === '' ? '—' : money(Number(v))),
    text: (v) => (v === null || v === undefined || v === '' ? '' : String(Math.round(Number(v)))),
  }
}

const requiredDateCol = dateCol('required_date', 'Required Date')
// PPC/Store is a date in the source data, not a PPC-vs-Store category.
const ppcStoreCol = dateCol('ppc_store', 'PPC / Store')

// One shared 'value' column across all four types (so mixing e.g. Purchases
// + Inventory into one table still collapses to a single "Value" column
// instead of two), formatted per row by its own type — Inventory's value is
// a quantity, everything else is PKR. For imports this is now the LINE's own
// value (quantity x unit price), not the whole consignment's; for logistics
// it stays the ORDER's total cost, repeated on every line of that order (see
// app/reports/serializers.py — logistics has no per-item cost to draw a
// genuine line figure from).
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
    dateCol('po_date', 'PO Date'),
    plainCol('bill_no', 'Bill No'),
    plainCol('dc_no', 'DC No'),
    plainCol('item_code', 'Item Code'),
    plainCol('item', 'Item'),
    plainCol('specification', 'Specification'),
    plainCol('supplier', 'Supplier'),
    plainCol('branch', 'Branch'),
    plainCol('category', 'Category'),
    ppcStoreCol,
    plainCol('mop', 'Mode of Purchase'),
    plainCol('sourcing_officer', 'Sourcing Officer'),
    plainCol('quantity', 'Quantity', 'right'),
    valueCol,
    dateCol('date', 'Date'),
    requiredDateCol,
    statusCol,
  ],
  // One row per consignment ITEM, not per consignment — header fields
  // (supplier, clearing agent, incoterm, ...) repeat on every line of the
  // same consignment; line fields (HS code, quantity, ELC/ALC, ...) are each
  // that line's own value. See app/reports/serializers.py's ROW_KEYS comment.
  imports: [
    typeCol,
    plainCol('ref', 'Reference'),
    plainCol('item_code', 'Item Code'),
    plainCol('item', 'Item'),
    plainCol('hs_code', 'HS Code'),
    plainCol('batch_no', 'Batch No'),
    plainCol('quantity', 'Quantity', 'right'),
    plainCol('unit_of_measurement', 'UoM'),
    numCol('unit_price', 'Unit Price'),
    valueCol,
    numCol('exchange_rate', 'Exchange Rate', 4),
    moneyCol('elc', 'ELC'),
    moneyCol('alc', 'ALC'),
    plainCol('requisition_type', 'Requisition Type'),
    plainCol('reference_number', 'Reference Number'),
    plainCol('job_number', 'Job Number'),
    plainCol('mo_number', 'MO Number'),
    numCol('gross_weight', 'Gross Weight', 3),
    plainCol('supplier', 'Supplier'),
    plainCol('country', 'Country'),
    plainCol('branch', 'Branch'),
    plainCol('works', 'Works'),
    plainCol('category', 'Category'),
    plainCol('clearing_agent', 'Clearing Agent'),
    plainCol('loading_port', 'Loading Port'),
    plainCol('delivery_port', 'Delivery Port'),
    plainCol('incoterm', 'Incoterm'),
    plainCol('currency', 'Currency'),
    plainCol('consignment_type', 'Consignment Type'),
    plainCol('mode_of_shipment', 'Mode of Shipment'),
    plainCol('payment_instrument', 'Payment Instrument'),
    plainCol('gd_number', 'GD Number'),
    dateCol('gd_filing_date', 'GD Filing Date'),
    dateCol('gate_out_date', 'Gate Out Date'),
    dateCol('po_date', 'PO Date'),
    dateCol('etd', 'ETD'),
    dateCol('eta_works', 'ETA Works'),
    statusCol,
    dateCol('date', 'Date'),
  ],
  inventory: [
    typeCol,
    plainCol('ref', 'Item Code'),
    plainCol('item', 'Item'),
    plainCol('branch', 'Branch'),
    plainCol('category', 'Category'),
    plainCol('specs', 'Specs'),
    plainCol('rank', 'ABC Rank'),
    valueCol,
    plainCol('stock_qty', 'Stock Qty', 'right'),
    plainCol('hold_qty', 'Hold Qty', 'right'),
    plainCol('reorder_level', 'Reorder Level', 'right'),
    statusCol,
    plainCol('reorder_status', 'Reorder Status'),
  ],
  // One row per order ITEM, not per order — header fields (customer,
  // incoterm, freight costs, ...) repeat on every line of the same order;
  // line fields (job no, quantity, RFD dates, ...) are each that line's own
  // value. `value`/individual cost columns stay order-level (see valueCol).
  logistics: [
    typeCol,
    plainCol('ref', 'Shipment Ref'),
    plainCol('job_number', 'Job Number'),
    plainCol('item', 'Item'),
    plainCol('quantity', 'Quantity', 'right'),
    numCol('unit_weight', 'Unit Weight', 3),
    numCol('gross_weight', 'Gross Weight', 3),
    dateCol('planned_rfd_date', 'Planned RFD'),
    dateCol('actual_rfd_date', 'Actual RFD'),
    plainCol('customer', 'Customer'),
    plainCol('country', 'Country'),
    plainCol('origin_city', 'Origin City'),
    plainCol('origin_province', 'Origin Province'),
    plainCol('order_type', 'Order Type'),
    plainCol('department', 'Department'),
    plainCol('shipment_mode', 'Shipment Mode'),
    plainCol('batch_label', 'Batch'),
    plainCol('incoterm', 'Incoterm'),
    plainCol('pol', 'Port of Loading'),
    plainCol('pod', 'Port of Discharge'),
    plainCol('shipping_line', 'Shipping Line'),
    plainCol('clearing_agent', 'Clearing Agent'),
    plainCol('booking_no', 'Booking No'),
    statusCol,
    plainCol('stage', 'Stage'),
    valueCol,
    numCol('cost_per_kg', 'Cost / Kg'),
    moneyCol('packing_cost', 'Packing Cost'),
    moneyCol('transportation_charges', 'Transportation'),
    moneyCol('container_detention', 'Container Detention'),
    moneyCol('insurance', 'Insurance'),
    moneyCol('trucking_lhr_to_khi', 'Trucking (LHR-KHI)'),
    moneyCol('fumigation_cost', 'Fumigation'),
    moneyCol('lashing', 'Lashing'),
    moneyCol('qfl_charges', 'QFL Charges'),
    moneyCol('qfl_container_movement', 'QFL Container Movement'),
    moneyCol('custom_clearance_charges', 'Custom Clearance'),
    moneyCol('port_charges', 'Port Charges'),
    moneyCol('dhl_charges', 'DHL Charges'),
    moneyCol('sea_air_freight', 'Sea/Air Freight'),
    dateCol('date', 'Date'),
    dateCol('etd_sailing_date', 'ETD Sailing'),
    dateCol('cro_arrival_date', 'CRO Arrival'),
    dateCol('actual_arrival_date', 'Actual Arrival'),
    dateCol('gate_out_date', 'Gate Out Date'),
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
