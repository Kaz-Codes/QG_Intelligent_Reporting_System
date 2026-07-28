/**
 * Fake data for building the frontend before the real backend is ready —
 * same purpose as the old Streamlit project's stubs/fake_data.py. Every
 * mock function here mirrors the SHAPE of what a real API will eventually
 * return, so pages don't change when the swap happens, only these modules.
 *
 * A seeded PRNG keeps the fake data stable across reloads (same spirit as
 * the old `random.seed(42)`) so charts don't jump around while you're
 * reviewing the UI.
 */

export function mulberry32(seed: number) {
  let s = seed
  return function random() {
    s |= 0
    s = (s + 0x6d2b79f5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function randInt(rng: () => number, min: number, max: number): number {
  return Math.floor(rng() * (max - min + 1)) + min
}

export function choice<T>(rng: () => number, arr: readonly T[]): T {
  return arr[Math.floor(rng() * arr.length)]
}

export function recentDate(rng: () => number, maxDaysAgo = 120): Date {
  const d = new Date()
  d.setDate(d.getDate() - randInt(rng, 0, maxDaysAgo))
  return d
}

export const BRANCHES = ['Lahore', 'Karachi', 'Faisalabad', 'Multan'] as const
export const SUPPLIERS = [
  'Alpha Traders', 'Beta Metals', 'Gamma Supply Co', 'Delta Industrial', 'Epsilon Corp',
] as const
export const ITEMS = [
  'Tap Handle 1/2"', 'Thread Gauge', 'Bolt Tensioner', 'Plain Washer M16', 'Three Jaws Chuck',
] as const
export const CUSTOMERS = [
  'Bestway Cement', 'Maple Leaf Cement', 'Fauji Cement', 'DG Khan Cement',
] as const
export const ITEM_CATEGORIES = [
  'Fasteners', 'Tools', 'Bearings', 'Electricals', 'Consumables',
] as const
export const MODES_OF_PURCHASE = ['Local Purchase', 'Import', 'Direct Purchase', 'Tender'] as const
export const SOURCING_OFFICERS = ['Ali Raza', 'Sara Khan', 'Bilal Ahmed', 'Nadia Iqbal'] as const
