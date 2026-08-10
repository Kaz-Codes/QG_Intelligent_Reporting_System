import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'

/**
 * The timeline control every dashboard shares.
 *
 * The backend defaults to the CURRENT MONTH when no range is sent, so "This
 * month" here is simply the absence of both dates — the front end never has to
 * compute the default itself and therefore cannot disagree with the server
 * about what "this month" means.
 *
 * The presets are the ranges people actually ask for. Anything else goes in the
 * two date boxes.
 */

export interface Period {
  from: string
  to: string
}

export const EMPTY_PERIOD: Period = { from: '', to: '' }

function iso(d: Date) {
  return d.toISOString().slice(0, 10)
}

function monthsBack(months: number): Period {
  const to = new Date()
  const from = new Date()
  from.setMonth(from.getMonth() - months)
  return { from: iso(from), to: iso(to) }
}

function thisYear(): Period {
  const now = new Date()
  return { from: `${now.getFullYear()}-01-01`, to: iso(now) }
}

/** `range` is the source's REAL extent, from coverage. "All time" uses it
 *  rather than a hardcoded wide window: a fixed 2000-01-01 put a date in the
 *  From box for a year the data has never contained, and made the backend
 *  bucket 372 mostly-empty months. Falls back to a wide range only until
 *  coverage has loaded. */
function presets(range?: { earliest: string | null; latest: string | null }) {
  return [
    { label: 'This month', value: () => EMPTY_PERIOD },
    { label: 'Last 3 months', value: () => monthsBack(3) },
    { label: 'Last 12 months', value: () => monthsBack(12) },
    { label: 'This year', value: () => thisYear() },
    {
      label: 'All data',
      value: () => ({
        from: range?.earliest ?? '2000-01-01',
        to: range?.latest ?? iso(new Date()),
      }),
    },
  ]
}

export function PeriodFilter({
  period, onChange, label = 'Period', range,
}: {
  period: Period
  onChange: (p: Period) => void
  label?: string
  /** The source's real date extent, so "All data" means exactly that. */
  range?: { earliest: string | null; latest: string | null }
}) {
  const isThisMonth = !period.from && !period.to
  const PRESETS = presets(range)

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label>{label}</Label>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => {
            const next = p.value()
            const active = p.label === 'This month'
              ? isThisMonth
              : !isThisMonth && period.from === next.from && period.to === next.to
            return (
              <Button
                key={p.label}
                type="button"
                variant={active ? 'default' : 'outline'}
                className="h-8 px-2.5 text-xs"
                onClick={() => onChange(next)}
              >
                {p.label}
              </Button>
            )
          })}
        </div>
      </div>

      <div className="flex items-end gap-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="period-from" className="text-xs">From</Label>
          <Input
            id="period-from"
            type="date"
            className="h-8 w-36"
            value={period.from}
            onChange={(e) => onChange({ ...period, from: e.target.value })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="period-to" className="text-xs">To</Label>
          <Input
            id="period-to"
            type="date"
            className="h-8 w-36"
            value={period.to}
            onChange={(e) => onChange({ ...period, to: e.target.value })}
          />
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------------- */

export interface Coverage {
  date_field: string
  earliest: string | null
  latest: string | null
  rows_in_period: number
  rows_total: number
  is_empty: boolean
  latest_month: string | null
}

export interface ResolvedPeriod {
  from: string | null
  to: string | null
  kind: string
  label: string
}

/**
 * States, in plain words, which window the figures below describe — and when
 * that window is empty, says so and offers the month that is not.
 *
 * This is the difference between a dashboard reading "Rs 0" (which looks like
 * a collapse in spend) and reading "no purchases in August 2026; the latest
 * data is 23 Jan 2026". The loaded purchases stop in January, so this is the
 * normal case on that screen, not an edge case.
 */
export function PeriodSummary({
  period, coverage, onJumpToLatest,
}: {
  period: ResolvedPeriod
  coverage: Coverage
  onJumpToLatest?: (p: Period) => void
}) {
  if (coverage.is_empty) {
    return (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-3 py-2 text-xs text-[var(--color-watch)]">
        <span className="font-semibold">No data in {period.label}.</span>
        <span>
          This source holds {coverage.rows_total.toLocaleString()} records by{' '}
          {coverage.date_field}
          {coverage.earliest && coverage.latest
            ? `, from ${coverage.earliest} to ${coverage.latest}`
            : ''}
          .
        </span>
        {coverage.latest_month && coverage.latest && onJumpToLatest && (
          <button
            className="underline underline-offset-2"
            onClick={() => onJumpToLatest({ from: coverage.latest_month!, to: coverage.latest! })}
          >
            Show the latest month with data
          </button>
        )}
      </div>
    )
  }

  return (
    <p className="text-xs text-muted">
      Showing <span className="font-medium text-ink">{period.label}</span> —{' '}
      {coverage.rows_in_period.toLocaleString()} of{' '}
      {coverage.rows_total.toLocaleString()} records, by {coverage.date_field}.
      {coverage.latest && <> Data available to {coverage.latest}.</>}
    </p>
  )
}
