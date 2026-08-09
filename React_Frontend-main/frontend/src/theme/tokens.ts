/**
 * Design tokens — port of the Streamlit project's components/theme.py.
 * Colors here must stay in sync with the CSS variables in src/index.css
 * (JS values are needed for Recharts, which can't read Tailwind classes).
 */

export const BRAND = '#0369A1'
export const BRAND_DEEP = '#075985'
export const BRAND_LIGHT = '#7DC4EA'
/** Retained name for call-site compatibility; now a deep navy rather than a
 * violet — used as the third chart hue and the trend-line dot. */
export const VIOLET = '#1E3A5F'
export const GOLD = '#A16207'

/** Steel blue -> brass -> navy -> supporting tints. Six hues that stay
 * distinguishable in a stacked bar without turning a report into a rainbow. */
export const CHART_SEQUENCE = [BRAND, GOLD, VIOLET, '#0E7490', '#8C6D1F', '#7C93AD']

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

/** Restrained industrial set — steel blue, petrol, brass, navy, slate.
 * Every module still reads as distinct, but the palette holds together as
 * one system instead of twelve unrelated hues. */
export const MODULE_ACCENTS: Record<PageKey, string> = {
  dashboard: BRAND,
  purchases: '#A16207',
  inventory: '#0F766E',
  imports: '#0E7490',
  importsStatus: '#1E3A5F',
  logisticsStatus: '#475569',
  truckingStatus: '#7C4A11',
  dataEntry: '#0E7490',
  logistics: '#1E3A5F',
  reports: '#475569',
  assistant: '#0369A1',
  userManagement: '#64748B',
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
  navy: '#0F172A', navyDeep: '#020617', goldSoft: '#F0E4BE', brandSoft: '#E0F2FE',
  ink: '#0F172A', muted: '#475569', line: '#DDE3EC',
  surface: '#FFFFFF', canvas: '#F8FAFC', canvasAlt: '#EEF2F7', sidebarBg: '#FFFFFF',
  risk: '#B42318', riskBg: '#FEF0EF', watch: '#A15C07', watchBg: '#FEF6E7',
  healthy: '#17694A', healthyBg: '#E7F5EF', info: '#0F5C8F', infoBg: '#EAF3FA',
}

export const DARK: Palette = {
  navy: '#E6EDF6', navyDeep: '#020617', goldSoft: '#7A5B14', brandSoft: '#0C2A3D',
  ink: '#E6EDF6', muted: '#94A3B8', line: '#253044',
  surface: '#131A26', canvas: '#080B12', canvasAlt: '#1A2130', sidebarBg: '#0D131E',
  risk: '#F58F82', riskBg: '#2A1B1A', watch: '#E3AC55', watchBg: '#2A2317',
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
