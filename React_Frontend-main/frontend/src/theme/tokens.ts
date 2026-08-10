/**
 * Design tokens — port of the Streamlit project's components/theme.py.
 * Colors here must stay in sync with the CSS variables in src/index.css
 * (JS values are needed for Recharts, which can't read Tailwind classes).
 */

export const BRAND = '#A16207'
export const BRAND_DEEP = '#7C4A05'
export const BRAND_LIGHT = '#E0A50B'
/** Retained name for call-site compatibility; now warm graphite — used as the
 * third chart hue and the trend-line dot. */
export const VIOLET = '#3B4654'
/** The literal Qadri Group logo gold. Accent bars, focus rings and fills with
 * dark text only — 1.42:1 on white, so never for text or white-on-gold. */
export const GOLD = '#F8D807'

/** Gold leads (brand), then maximally-separated hues. A six-step warm ramp
 * would be on-brand and unreadable — categorical series need hue separation
 * more than they need to match the logo. Chart gold is darkened to #B87F09
 * so bars clear 3:1 against the canvas. */
export const CHART_SEQUENCE = ['#B87F09', '#0F766E', '#3B4654', '#B4531A', '#3E6E9E', '#8A6E2F']

export type PageKey =
  | 'dashboard'
  | 'purchases'
  | 'inventory'
  | 'imports'
  | 'importsStatus'
  | 'logisticsStatus'
  | 'truckingStatus'
  | 'dataEntry'
  | 'logistics'
  | 'reports'
  | 'assistant'
  | 'userManagement'
  | 'masters'

/** Restrained industrial set anchored on brand gold — gold, burnt orange,
 * petrol, steel, graphite, bronze.
 * Every module still reads as distinct, but the palette holds together as
 * one system instead of twelve unrelated hues. */
export const MODULE_ACCENTS: Record<PageKey, string> = {
  dashboard: BRAND,
  purchases: '#B4531A',
  inventory: '#0F766E',
  imports: '#3E6E9E',
  importsStatus: '#3B4654',
  logisticsStatus: '#5C5346',
  truckingStatus: '#8A6E2F',
  dataEntry: '#0F766E',
  logistics: '#3B4654',
  reports: '#5C5346',
  assistant: BRAND,
  userManagement: '#6B6156',
  // Reference-data management — reuses inventory's petrol hue (same
  // convention the pre-rebrand palette used: masters === inventory), rather
  // than adding a seventh hue to an already six-step ramp.
  // (Both sides of this merge independently chose #0F766E; only the comment
  // differed, and this one names the convention it follows.)
  masters: '#0F766E',
}

export interface Palette {
  navy: string
  navyDeep: string
  goldSoft: string
  brandSoft: string
  ink: string
  muted: string
  line: string
  surface: string
  canvas: string
  canvasAlt: string
  sidebarBg: string
  risk: string
  riskBg: string
  watch: string
  watchBg: string
  healthy: string
  healthyBg: string
  info: string
  infoBg: string
}

export const LIGHT: Palette = {
  navy: '#1A1614', navyDeep: '#0A0806', goldSoft: '#FDF4D3', brandSoft: '#FBF0D9',
  ink: '#1A1614', muted: '#6B6156', line: '#E6DFD2',
  surface: '#FFFFFF', canvas: '#FAF8F5', canvasAlt: '#F3EFE8', sidebarBg: '#FFFFFF',
  risk: '#B42318', riskBg: '#FBEBE9', watch: '#C2410C', watchBg: '#FDF2E3',
  healthy: '#17694A', healthyBg: '#E7F5EF', info: '#1F5F8B', infoBg: '#E9F1F7',
}

export const DARK: Palette = {
  navy: '#F2EDE4', navyDeep: '#0A0806', goldSoft: '#4A3708', brandSoft: '#2E2208',
  ink: '#F2EDE4', muted: '#A79A88', line: '#332C21',
  surface: '#17140F', canvas: '#0A0908', canvasAlt: '#211C15', sidebarBg: '#100E0A',
  risk: '#F58F82', riskBg: '#2A1A18', watch: '#F0A868', watchBg: '#2A2015',
  healthy: '#4FD394', healthyBg: '#14281F', info: '#7FC0EA', infoBg: '#10222F',
}

type StatusRole = 'risk' | 'watch' | 'healthy'

// Same placeholder business rule as the Streamlit version's _STATUS_ROLES —
// terminal states aren't confirmed by the business yet.
const STATUS_ROLES: Record<string, StatusRole> = {
  delayed: 'risk', 'pending clearance': 'risk', 'below reorder': 'risk',
  'out of stock': 'risk', critical: 'risk', 'order cancelled': 'risk', incomplete: 'risk',
  pending: 'watch', 'in transit': 'watch', watch: 'watch',
  'under production': 'watch', 'ready awaiting sailing': 'watch',
  'under custom clearance': 'watch', 'costing in process': 'watch',
  'lc in process': 'watch', 't/t in process': 'watch', 'under de-stuffing': 'watch',
  sailing: 'watch', 'at qfl': 'watch', 'at port': 'watch',
  'pending packing': 'watch', 'in progress': 'watch', 'near complete': 'watch',
  // Logistics Status labels (EXPORT_STATUSES / LOCAL_STATUSES in
  // features/logisticsStatus/schema.ts) — additive only, nothing above changed.
  'under packing': 'watch', transportation: 'watch', 'under shipping arrangement': 'watch',
  'on water': 'watch',
  completed: 'healthy', cleared: 'healthy', ok: 'healthy', delivered: 'healthy',
  healthy: 'healthy', 'arrived at works': 'healthy', 'arrived at qfl': 'healthy', complete: 'healthy',
}

/** (fg, bg) for a status label, resolved against the given palette. */
export function statusColors(label: string, palette: Palette): [string, string] {
  const role = STATUS_ROLES[label.trim().toLowerCase()]
  if (role === 'risk') return [palette.risk, palette.riskBg]
  if (role === 'watch') return [palette.watch, palette.watchBg]
  if (role === 'healthy') return [palette.healthy, palette.healthyBg]
  return [palette.info, palette.infoBg]
}
