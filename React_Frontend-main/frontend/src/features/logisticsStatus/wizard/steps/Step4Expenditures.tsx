import { useEffect, useRef } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { packingCostRollup, type LogisticsDraft, type LogisticsPackage } from '../../schema'

// The expenditure set depends on order type. Kept as data (not scattered
// if-blocks) so adding a cost line later is a one-row change — the same
// "single rules object per screen" convention the imports module uses.
const EXPORT_COSTS: { name: keyof LogisticsDraft; label: string }[] = [
  { name: 'packingCost', label: 'Packing Cost' },
  { name: 'insurance', label: 'Insurance' },
  { name: 'truckingLhrToKhi', label: 'Trucking (Lhr → Khi / QFL)' },
  { name: 'fumigationCost', label: 'Fumigation Cost' },
  { name: 'lashing', label: 'Lashing' },
  { name: 'qflCharges', label: 'QFL Charges' },
  { name: 'qflContainerMovement', label: 'QFL Transportation (Port → QFL → Port)' },
  { name: 'customClearanceCharges', label: 'Custom Clearance Charges' },
  { name: 'portCharges', label: 'Port Charges' },
  { name: 'containerDetention', label: 'Container Detention' },
  { name: 'dhlCharges', label: 'DHL Charges' },
  { name: 'seaAirFreight', label: 'Sea Freight / Air Freight' },
]

const LOCAL_COSTS: { name: keyof LogisticsDraft; label: string }[] = [
  { name: 'packingCost', label: 'Packing Cost' },
  { name: 'transportationCharges', label: 'Transportation Charges' },
  { name: 'containerDetention', label: 'Container Detention' },
]

const rs = (v: number) => `Rs. ${v.toFixed(2)}`

/** Raw form state again — `''` from a cleared number input is not 0. */
function asNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

// Written out in full, never built by interpolation: Tailwind scans source
// for literal class names, so a composed `text-[var(--color-${tone})]` would
// simply not be generated and the figure would lose its colour.
const TONE_CLASS = {
  ink: 'text-ink',
  healthy: 'text-[var(--color-healthy)]',
  risk: 'text-[var(--color-risk)]',
} as const

/** One rolled-up figure with the count it was computed over. The basis is not
 *  decoration: several of these rest on a subset of the packages, and a bare
 *  total would read as a fact about the whole order. */
function RollupFigure({
  label, value, basis, tone = 'ink',
}: {
  label: string
  value: string
  basis: string
  tone?: keyof typeof TONE_CLASS
}) {
  const color = TONE_CLASS[tone]
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${color}`}>{value}</span>
      <span className="text-[11px] text-muted">{basis}</span>
    </div>
  )
}

/**
 * Step 4 — Expenditures.
 *
 * PACKING IS ROLLED UP, NOT RE-KEYED. The Packing step already holds a quoted
 * and an actual cost per package, so the order-level packing figure is derived
 * from them (schema.packingCostRollup) and shown beside the input rather than
 * being an unrelated number the operator invents a second time. It recomputes
 * live off the packages in form state — no save, no refetch.
 *
 * The order-level field DEFAULTS to the rolled-up actual but is never forced:
 * it only self-fills while it is still empty, so opening a saved order never
 * silently rewrites the figure someone already committed. An operator can
 * override it — they sometimes have a reason — but an override that disagrees
 * with the package detail says so, and by how much, instead of quietly
 * standing in for it.
 *
 * Nothing here is persisted beyond the single `packingCost` column that
 * already existed. The model's comment that these totals are "worked out on
 * the front end, never stored" still holds.
 */
export function Step4Expenditures() {
  const { register, control, setValue, formState: { errors } } = useFormContext<LogisticsDraft>()
  const orderType = useWatch({ control, name: 'orderType' })
  const costs = orderType === 'Export' ? EXPORT_COSTS : LOCAL_COSTS

  // Provisional running total across the visible lines. Partial data produces
  // a provisional figure marked with an asterisk, never a blank.
  const values = useWatch({ control, name: costs.map((c) => c.name) as (keyof LogisticsDraft)[] })
  const total = (values as (number | undefined)[]).reduce<number>((s, v) => s + (Number(v) || 0), 0)

  // Live off form state, so editing a package cost in step 2 moves these
  // without a save.
  const packages = (useWatch({ control, name: 'packages' }) ?? []) as LogisticsPackage[]
  const rollup = packingCostRollup(packages)

  const packingCost = useWatch({ control, name: 'packingCost' })
  const typedPacking = asNumber(packingCost)

  // DRAFT_DEFAULT_VALUES starts this at 0, so 0 reads as "nothing entered yet".
  const packingUnset = typedPacking === null || typedPacking === 0
  const touched = useRef(false)

  // Seed the order figure from the packages — but only into an empty field,
  // and never marking the form dirty. Overwriting a saved value here would
  // change committed data just by opening the step, and a dirty flag would
  // trip the wizard's unsaved-changes prompt on a value nobody typed.
  useEffect(() => {
    if (touched.current || !packingUnset || rollup.actual === null) return
    setValue('packingCost', rollup.actual, { shouldDirty: false })
  }, [rollup.actual, packingUnset, setValue])

  const overrides = !packingUnset
    && rollup.actual !== null
    && Math.abs((typedPacking ?? 0) - rollup.actual) > 0.005
  const overrideBy = (typedPacking ?? 0) - (rollup.actual ?? 0)

  const otherCosts = costs.filter((c) => c.name !== 'packingCost')
  const packingField = register('packingCost', { valueAsNumber: true })

  return (
    <div className="flex flex-col gap-4">
      {/* Packing — the one cost line with package-level detail behind it. */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Packing cost
        </h3>

        <div className="flex flex-col gap-3 p-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <RollupFigure
              label="Quoted (packages)"
              value={rollup.quoted === null ? '—' : rs(rollup.quoted)}
              basis={rollup.packages === 0
                ? 'no packages yet'
                : `${rollup.quotedBasis} of ${rollup.packages} package${rollup.packages === 1 ? '' : 's'} quoted`}
            />
            <RollupFigure
              label="Actual (packages)"
              value={rollup.actual === null ? '—' : rs(rollup.actual)}
              basis={rollup.packages === 0
                ? 'no packages yet'
                : `${rollup.actualBasis} of ${rollup.packages} package${rollup.packages === 1 ? '' : 's'} costed`}
            />
            {/* Sign is spelled out, not left as a minus the reader has to
                interpret: these two mean opposite things to the business. */}
            <RollupFigure
              label={rollup.savings !== null && rollup.savings < 0 ? 'Overrun' : 'Savings'}
              value={rollup.savings === null
                ? '—'
                : rollup.savings < 0
                  ? `Over by ${rs(Math.abs(rollup.savings))}`
                  : `Saved ${rs(rollup.savings)}`}
              tone={rollup.savings === null ? 'ink' : rollup.savings < 0 ? 'risk' : 'healthy'}
              basis={rollup.savingsBasis === 0
                ? 'needs a package priced both ways'
                : `across ${rollup.savingsBasis} package${rollup.savingsBasis === 1 ? '' : 's'} priced both ways`}
            />
          </div>

          {/* A partial actual must never be mistaken for the final one. */}
          {rollup.actual !== null && !rollup.actualComplete && (
            <p className="rounded-lg border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-3 py-2 text-xs text-[var(--color-watch)]">
              Partial — {rollup.actualBasis} of {rollup.packages} packages costed. The remaining
              {' '}{rollup.packages - rollup.actualBasis} have no actual cost yet and are left out
              rather than counted as zero, so this total will still rise.
            </p>
          )}

          <div className="flex flex-col gap-1.5 sm:max-w-xs">
            <Label htmlFor="packingCost">Packing Cost on this order (Rs.)</Label>
            <Input
              id="packingCost"
              type="number"
              step="0.01"
              {...packingField}
              // Registered once above; this only marks the field as engaged so
              // the seeding effect stops competing with what is being typed.
              onChange={(e) => { touched.current = true; return packingField.onChange(e) }}
            />
            {errors.packingCost && <p className="text-xs text-risk">{String(errors.packingCost?.message)}</p>}
            <p className="text-xs text-muted">
              {rollup.actual === null
                ? 'No package has an actual cost yet — enter the order figure by hand.'
                : 'Defaults to the packages’ actual total; override it if the order was billed differently.'}
            </p>
          </div>

          {/* Not blocked — just never silently accepted. */}
          {overrides && (
            <p className="rounded-lg border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-3 py-2 text-xs text-[var(--color-watch)]">
              This differs from the package roll-up by {rs(Math.abs(overrideBy))}
              {' '}({overrideBy > 0 ? 'higher' : 'lower'} than the {rs(rollup.actual ?? 0)} costed across
              {' '}{rollup.actualBasis} package{rollup.actualBasis === 1 ? '' : 's'}).
              {!rollup.actualComplete && ' Some packages are still uncosted, which may explain it.'}
            </p>
          )}
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
        {otherCosts.map(({ name, label }) => (
          <div key={name} className="flex flex-col gap-1.5">
            <Label htmlFor={name}>{label} (Rs.)</Label>
            <Input
              id={name}
              type="number"
              step="0.01"
              {...register(name as keyof LogisticsDraft, { valueAsNumber: true })}
            />
            {errors[name] && <p className="text-xs text-risk">{String(errors[name]?.message)}</p>}
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between rounded-lg border border-line bg-canvas-alt px-4 py-3">
        <span className="text-sm font-medium text-ink">Total Expenditure*</span>
        <span className="text-sm font-semibold tabular-nums text-ink">{rs(total)}</span>
      </div>
      <p className="-mt-2 text-xs text-muted">
        *Provisional — sums the {orderType === 'Export' ? 'export' : 'local'} cost lines entered so far,
        packing included.
      </p>
    </div>
  )
}
