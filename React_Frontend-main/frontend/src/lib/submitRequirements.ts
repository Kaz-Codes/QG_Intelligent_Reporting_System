/**
 * What still blocks Submit, and where to go and fix it.
 *
 * Each wizard module builds its own list (see submitRequirements() in the
 * three schema.ts files); this is the shape they share and the one place the
 * disabled-button tooltip is worded.
 *
 *
 * THESE MIRROR THE BACKEND'S submission_errors(), NOT THE ZOD SUBMIT SCHEMA.
 *
 * Both exist and they are not identical — the differences are written up in
 * each module's submitRequirements(). The backend is what actually refuses a
 * submission, so it is what a "what still blocks Submit" list has to predict.
 * A banner derived from a stricter frontend rule would disable Submit for
 * something the server would happily accept; one derived from a laxer rule
 * would enable it and then hand back a 422, which is exactly the surprise
 * this feature exists to remove.
 */

export interface SubmitRequirement {
  /** Near enough the backend's own wording, so the banner and a 422 that
   *  slips through anyway do not describe the same gap in two ways. */
  message: string
  /** The wizard step that owns the field. */
  step: number
  /** That step's label, for the "Go to Consignment" link. */
  stepLabel: string
}

/** The Submit button's disabled reason: the same list, flattened. Named
 *  rather than written inline in three wizards, so the tooltip cannot end up
 *  saying something different from the banner directly above it. */
export function requirementsTooltip(
  requirements: SubmitRequirement[],
): string | undefined {
  if (requirements.length === 0) return undefined
  return `Still needed to submit:\n• ${requirements.map((r) => r.message).join('\n• ')}`
}
