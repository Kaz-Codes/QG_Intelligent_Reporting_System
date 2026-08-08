// Tappable answer chips for when the assistant's route is "clarify" — e.g.
// two item codes share a name and it needs to know which one. Same visual
// language as the landing page's suggested-question buttons.

export function ClarifyOptions({
  options,
  onPick,
  disabled,
}: {
  options: string[]
  onPick: (option: string) => void
  disabled?: boolean
}) {
  if (!options.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {options.map((opt) => (
        <button
          key={opt}
          disabled={disabled}
          onClick={() => onPick(opt)}
          className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-light hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50"
        >
          {opt}
        </button>
      ))}
    </div>
  )
}
