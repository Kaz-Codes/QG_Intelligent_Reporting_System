import { getPurchases } from './purchases'
import { getStock } from './inventory'
import { getImports } from './imports'
import { money } from '@/lib/format'

/**
 * TEMPORARY frontend mock for QadriBot. The real assistant is a text-to-SQL
 * agent owned by a teammate (a natural-language question -> read-only SQL ->
 * answer + table/chart). Here we just keyword-match a few canned answers over
 * the existing mock data so the chat UI can be built and demoed. Swap this
 * one file's body for a real API call later — the chat UI never changes.
 */

export interface BotTableColumn {
  key: string
  label: string
  align?: 'left' | 'right'
}

export interface BotAnswer {
  text: string
  table?: { columns: BotTableColumn[]; rows: Record<string, unknown>[] }
  chart?: { labels: string[]; values: number[] }
}

export const SUGGESTED_QUERIES = [
  'Which purchase orders are delayed?',
  'Which supplier has the most delays?',
  'Which items are below reorder level?',
  'Show imports pending clearance',
]

function topDelaysBySupplier() {
  const delayed = getPurchases({ status: ['Delayed'] })
  const counts = new Map<string, number>()
  for (const r of delayed) counts.set(r.supplier, (counts.get(r.supplier) ?? 0) + 1)
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
}

export function askQadriBot(question: string): BotAnswer {
  const q = question.toLowerCase()

  // Delayed purchase orders → table
  if (q.includes('delay') && (q.includes('order') || q.includes('purchase') || q.includes('po'))) {
    const delayed = getPurchases({ status: ['Delayed'] })
    return {
      text: `There are **${delayed.length} delayed purchase orders** in the current data. The most-delayed are shown below.`,
      table: {
        columns: [
          { key: 'po_number', label: 'PO Number' },
          { key: 'item', label: 'Item' },
          { key: 'supplier', label: 'Supplier' },
          { key: 'amount', label: 'Amount', align: 'right' },
        ],
        rows: delayed.slice(0, 10).map((r) => ({ ...r, amount: money(r.amount) })),
      },
    }
  }

  // Supplier with most delays → chart
  if (q.includes('supplier') && q.includes('delay')) {
    const ranked = topDelaysBySupplier()
    const top = ranked[0]
    return {
      text: top
        ? `**${top[0]}** has the most delayed orders (**${top[1]}**). Here's the breakdown across suppliers.`
        : 'No delayed orders in the current data.',
      chart: { labels: ranked.map((r) => r[0]), values: ranked.map((r) => r[1]) },
    }
  }

  // Below reorder / low stock → table
  if (q.includes('reorder') || q.includes('below') || q.includes('low stock') || q.includes('out of stock')) {
    const atRisk = getStock({ status: ['Below Reorder', 'Out of Stock'] })
    return {
      text: `**${atRisk.length} items** are at or below their reorder level right now.`,
      table: {
        columns: [
          { key: 'item_code', label: 'Item Code' },
          { key: 'item', label: 'Item' },
          { key: 'branch', label: 'Branch' },
          { key: 'available_qty', label: 'Available', align: 'right' },
          { key: 'stock_status', label: 'Status' },
        ],
        rows: atRisk.slice(0, 10) as unknown as Record<string, unknown>[],
      },
    }
  }

  // Imports pending clearance → table
  if (q.includes('import') && (q.includes('clearance') || q.includes('pending') || q.includes('customs'))) {
    const pending = getImports({ status: ['Under Custom Clearance', 'LC in Process'] })
    return {
      text: `**${pending.length} import shipments** are currently in customs clearance or LC processing.`,
      table: {
        columns: [
          { key: 'import_ref', label: 'Import Ref' },
          { key: 'supplier', label: 'Supplier' },
          { key: 'supplier_country', label: 'Country' },
          { key: 'current_status', label: 'Status' },
        ],
        rows: pending.slice(0, 10) as unknown as Record<string, unknown>[],
      },
    }
  }

  // Fallback
  return {
    text:
      "I'm a demo of **QadriBot** running on sample data — the live assistant (natural-language " +
      'questions answered from the real database) is being wired up by the team. Try one of the ' +
      'suggested questions, e.g. *“Which purchase orders are delayed?”*',
  }
}
