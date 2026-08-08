import { Disclosure } from '@/components/Disclosure'
import type { AssistantMessage } from '@/lib/chatbot/types'

// Collapsible panel exposing the backend's debug fields (route, SQL, rows,
// forecast, computation). Built on the app's own <Disclosure> (same role as
// Streamlit's st.expander(), already used elsewhere) so it looks like a
// native part of this app rather than a bolted-on debug widget. The chat
// works identically without it — delete freely if this ever needs to be
// business-user-only.

function Row({ label, children }: { label: string; children?: React.ReactNode }) {
  if (children === undefined || children === null || children === '') return null
  return (
    <div className="flex gap-2 py-1 text-xs">
      <span className="w-20 shrink-0 font-medium text-muted">{label}</span>
      <span className="text-ink">{children}</span>
    </div>
  )
}

function Pre({ children }: { children: string }) {
  return (
    <pre className="mt-1 overflow-x-auto rounded-lg bg-canvas-alt p-2 text-[11px] leading-relaxed text-ink">
      {children}
    </pre>
  )
}

export function DevDetailsPanel({ meta }: { meta: NonNullable<AssistantMessage['meta']> }) {
  const tags = [
    meta.route && `route: ${meta.route}`,
    meta.domain && `domain: ${meta.domain}`,
    typeof meta.rowCount === 'number' && `${meta.rowCount} rows`,
    meta.knowledgeInferred && 'knowledge inferred',
    meta.computationCode && 'ran computation',
    meta.analysisType && `analysis: ${meta.analysisType}`,
  ].filter(Boolean) as string[]

  return (
    <Disclosure title={tags.length ? `Details — ${tags.join(' · ')}` : 'Details'}>
      <div className="pb-3">
        <Row label="Route">{meta.route}</Row>
        <Row label="Domain">{meta.domain}</Row>
        <Row label="Intent">{meta.intent}</Row>
        <Row label="Rows">{typeof meta.rowCount === 'number' ? meta.rowCount : null}</Row>
        <Row label="Analysis">{meta.analysisType}</Row>
        <Row label="Knowledge">{meta.knowledgeInferred ? 'inferred from schema' : null}</Row>
        <Row label="Tables">{meta.tablesUsed?.length ? meta.tablesUsed.join(', ') : null}</Row>

        {meta.sql && (
          <div className="mt-1">
            <span className="text-xs font-medium text-muted">SQL</span>
            <Pre>{meta.sql}</Pre>
          </div>
        )}

        {meta.computationCode && (
          <div className="mt-1">
            <span className="text-xs font-medium text-muted">
              Computed{meta.computationExplanation ? ` — ${meta.computationExplanation}` : ''}
            </span>
            <Pre>{meta.computationCode}</Pre>
            {meta.computationResult !== null && meta.computationResult !== undefined && (
              <Pre>{JSON.stringify(meta.computationResult, null, 2)}</Pre>
            )}
          </div>
        )}

        {meta.forecast?.ok && (
          <div className="mt-1">
            <span className="text-xs font-medium text-muted">Forecast</span>
            <Pre>
              {JSON.stringify(
                {
                  method: meta.forecast.method,
                  direction: meta.forecast.direction,
                  confidence: meta.forecast.confidence,
                  r_squared: meta.forecast.r_squared,
                  projections: meta.forecast.projections,
                },
                null,
                2,
              )}
            </Pre>
          </div>
        )}

        {meta.error && <Row label="Note">{meta.error}</Row>}
      </div>
    </Disclosure>
  )
}
