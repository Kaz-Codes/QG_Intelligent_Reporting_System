export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

/** One entry of FastAPI's own automatic request-body validation 422 — sent
 *  when the JSON doesn't even satisfy the Pydantic schema's types (a string
 *  where a number was expected, a value outside a Field(gt=...) bound, an
 *  enum value that isn't one of the fixed options, ...). This is BEFORE any
 *  application code runs, so it's a different shape from any route's own
 *  HTTPException(detail=...). */
interface PydanticFieldError {
  loc: (string | number)[]
  msg: string
  type: string
}

function describeFieldErrors(errors: PydanticFieldError[]): string {
  return errors
    .map((e) => {
      // loc[0] is always the literal "body" for a JSON-body field; drop it so
      // the path reads as the field itself ("items.0.quantity", not
      // "body.items.0.quantity").
      const path = e.loc.slice(e.loc[0] === 'body' ? 1 : 0).join('.')
      return path ? `${path}: ${e.msg}` : e.msg
    })
    .join('; ')
}

export class ApiError extends Error {
  status: number
  /** The raw `detail` from the response body, before any stringifying. Most
   *  routes send a plain string (which is also what `.message` becomes); a
   *  few (imports' /submit, when validation fails) send a structured object
   *  — `{ message, errors: string[] }`; and a request body that fails
   *  Pydantic's own validation (before any route code runs) sends an ARRAY of
   *  `{loc, msg, type}`. Callers that need the full structure read `.detail`
   *  directly rather than parsing `.message` — for the object/array cases
   *  `.message` is only a best-effort summary, not the useless
   *  "[object Object]" a non-string message would otherwise coerce to. */
  detail: unknown

  constructor(status: number, detail: unknown) {
    let message: string
    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = detail.length ? describeFieldErrors(detail as PydanticFieldError[]) : `Request failed (${status})`
    } else {
      message = (detail as { message?: string })?.message ?? `Request failed (${status})`
    }
    super(message)
    this.status = status
    this.detail = detail
  }
}

/** Thin fetch wrapper for the real backend — `credentials: 'include'` so the
 * httpOnly session cookie /auth/login sets actually gets sent back on every
 * later call. Auth and user management go through here; the screens still on
 * mock data (lib/mockData) do not. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail)
  }

  return res.json() as Promise<T>
}

/** Same contract as apiFetch, but for a binary download (the Reports Excel
 * export) instead of JSON — no Content-Type request header, and the response
 * body is read as a Blob rather than parsed. */
export async function apiFetchBlob(path: string, init: RequestInit = {}): Promise<Blob> {
  const res = await fetch(`${BASE_URL}${path}`, { ...init, credentials: 'include' })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail)
  }

  return res.blob()
}
