const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Thin fetch wrapper for the real backend — `credentials: 'include'` so the
 * httpOnly session cookie /auth/login sets actually gets sent back on every
 * later call. Separate from the app's existing mock-data path (lib/mockData,
 * lib/mockAuth): only the modules wired to real endpoints go through this. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail ?? `Request failed (${res.status})`)
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
    throw new ApiError(res.status, body?.detail ?? `Request failed (${res.status})`)
  }

  return res.blob()
}
