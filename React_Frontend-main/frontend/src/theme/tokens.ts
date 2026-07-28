/**
 * Design tokens — port of the Streamlit project's components/theme.py.
 * Colors here must stay in sync with the CSS variables in src/index.css
 * (JS values are needed for Recharts, which can't read Tailwind classes).
 */

export const BRAND = '#4F46E5'
export const BRAND_DEEP = '#3730A3'
export const BRAND_LIGHT = '#818CF8'
export const VIOLET = '#8B5CF6'
export const GOLD = '#BF9000'

export const CHART_SEQUENCE = [BRAND, GOLD, VIOLET, '#4A6FA5', '#8C6D1F', '#7089B0']

export type PageKey =
  | 'dashboard'
  | 'purchases'
  | 'inventory'
  | 'imports'
  | 'importsStatus'
  | 'logisticsStatus'
  | 'dataEntry'
  | 'logistics'
  | 'reports'
  | 'assistant'
  | 'userManagement'

export const MODULE_ACCENTS: Record<PageKey, string> = {
  dashboard: BRAND,
  purchases: '#F59E0B',
  inventory: '#10B981',
  imports: '#0EA5E9',
  importsStatus: '#0891B2',
  logisticsStatus: '#E11D48',
  dataEntry: '#0891B2',
  logistics: '#FB7185',
  reports: '#06B6D4',
  assistant: '#8B5CF6',
  userManagement: '#64748B',
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
  navy: '#1F2D4E', navyDeep: '#16223C', goldSoft: '#E7D9A8', brandSoft: '#EEECFC',
  ink: '#1F2D4E', muted: '#5A6478', line: '#E6E8EF',
  surface: '#FFFFFF', canvas: '#F7F8FB', canvasAlt: '#F0F1F5', sidebarBg: '#FFFFFF',
  risk: '#C0392B', riskBg: '#FDECEC', watch: '#B9770E', watchBg: '#FEF6E7',
  healthy: '#1E8449', healthyBg: '#E9F7EF', info: '#2E5AAC', infoBg: '#EAF2FB',
}

export const DARK: Palette = {
  navy: '#F1F3F9', navyDeep: '#0B0E14', goldSoft: '#8A6D2A', brandSoft: '#241F3D',
  ink: '#F1F3F9', muted: '#9AA3B8', line: '#2A2E3D',
  surface: '#171A24', canvas: '#0E1017', canvasAlt: '#1D202C', sidebarBg: '#12141C',
  risk: '#F27E71', riskBg: '#2A1D1D', watch: '#E8AE4D', watchBg: '#2A2418',
  healthy: '#4ADE80', healthyBg: '#1A2A21', info: '#7CA6F0', infoBg: '#1B2436',
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
