/**
 * A UUID that works on the office LAN.
 *
 *
 * DO NOT REPLACE THIS WITH `crypto.randomUUID()`. IT WILL LOOK FINE AND SHIP A
 * BLANK PAGE.
 *
 * `crypto.randomUUID` is only exposed in a SECURE CONTEXT — HTTPS, or the
 * special-cased `localhost` / `127.0.0.1`. This app is served over plain HTTP
 * from a LAN address (http://192.168.x.x), which is neither, so the browser
 * does not define the method at all.
 *
 * That combination is unusually nasty:
 *
 *   * It works perfectly in development, because Vite serves on 127.0.0.1 and
 *     the browser treats that as secure. Every local check passes.
 *   * On the server it throws `TypeError: crypto.randomUUID is not a function`
 *     during startup, React never mounts, and the user gets a WHITE SCREEN with
 *     nothing on it. No error banner, no partial render — the failure is in the
 *     module graph, before any error boundary exists to catch it.
 *   * It affects every user on every page, so it does not look like a bug in a
 *     feature. It looks like the server is down.
 *
 * `crypto.getRandomValues`, by contrast, IS available in insecure contexts —
 * only `randomUUID` is restricted. So the fallback below is not a downgrade to
 * `Math.random()`: it is the same CSPRNG the browser would have used, formatted
 * into a v4 UUID by hand.
 */

/** Bytes 6 and 8 carry the version and variant bits that make a v4 UUID a v4
 *  UUID; everything else is random. */
function uuidV4FromRandomBytes(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)

  // version 4  -> high nibble of byte 6 is 0100
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  // variant 10 -> top two bits of byte 8
  bytes[8] = (bytes[8] & 0x3f) | 0x80

  const hex: string[] = []
  for (let i = 0; i < 16; i += 1) {
    hex.push(bytes[i].toString(16).padStart(2, '0'))
  }

  return (
    hex.slice(0, 4).join('') + '-' +
    hex.slice(4, 6).join('') + '-' +
    hex.slice(6, 8).join('') + '-' +
    hex.slice(8, 10).join('') + '-' +
    hex.slice(10, 16).join('')
  )
}

/**
 * A random v4 UUID, in every context this app is served from.
 *
 * Prefers the native implementation where the browser offers it — it is faster
 * and is the one the platform maintains — and falls back otherwise. The check
 * is `typeof ... === 'function'` rather than a truthiness test, because in an
 * insecure context the property is absent rather than falsy, and reading it off
 * a `crypto` that itself may be undefined would throw before the fallback could
 * run.
 */
export function uuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    return uuidV4FromRandomBytes()
  }

  // Nothing left to be cryptographic with. Reaching here means a browser far
  // older than anything this app supports, and a blank page would be a worse
  // answer than an id that is merely unique enough for a form row — which is
  // all these ids are ever used for (see the call sites: local wizard row keys,
  // swapped for real backend ids on the first save).
  throw new Error(
    'No Web Crypto available: cannot generate an id. This browser is too old ' +
    'for this application.',
  )
}
