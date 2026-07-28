import type { CSSProperties } from 'react'
import {
  Truck, Package, Ship, Plane, Warehouse, Boxes, ShoppingCart, Container,
  MapPin, Globe, ClipboardList, Receipt, Coins, BarChart3, PieChart, LineChart,
  MessageSquare, Sparkles, Gauge, TrendingUp, PackageCheck, Anchor, Forklift,
  type LucideIcon,
} from 'lucide-react'
import type { PageKey } from '@/theme/tokens'
import { MODULE_ACCENTS } from '@/theme/tokens'

/**
 * Ambient, subject-related animated backdrop. Each module drifts icons drawn
 * from its own field (imports → planes/ships/containers, inventory → boxes/
 * warehouses, ...) over a couple of slow aurora blobs tinted with the
 * module's accent. Purely decorative and low-opacity — it sits behind the
 * content (`-z-10`, `pointer-events-none`) and is `aria-hidden`.
 *
 * CSS-only motion (see index.css keyframes) — the safe, reliable path here.
 */

const MODULE_ICONS: Partial<Record<PageKey | 'login', LucideIcon[]>> = {
  dashboard: [Gauge, TrendingUp, BarChart3, Package, Truck],
  purchases: [ShoppingCart, Package, Receipt, ClipboardList, Coins],
  inventory: [Boxes, Package, Warehouse, PackageCheck, Forklift],
  imports: [Plane, Ship, Container, Globe, Anchor],
  importsStatus: [Container, Ship, Plane, ClipboardList, Anchor],
  logistics: [Truck, Ship, Container, MapPin, Package],
  reports: [BarChart3, PieChart, LineChart, ClipboardList, TrendingUp],
  assistant: [MessageSquare, Sparkles, BarChart3, Package, Truck],
  login: [Truck, Package, Ship, Plane, Warehouse, Boxes, ShoppingCart, Container, MapPin, Globe],
}

// Fixed scatter positions (deterministic, no RNG) so the field looks composed
// rather than random. Each: left/top %, size px, opacity, and per-icon drift
// tuning via CSS custom properties. Duration/delay varied so nothing marches
// in lockstep.
interface Spot {
  left: string
  top: string
  size: number
  opacity: number
  dur: string
  delay: string
  dx: string
  dy: string
  rot: string
}

const SPOTS: Spot[] = [
  { left: '6%', top: '18%', size: 46, opacity: 0.9, dur: '19s', delay: '0s', dx: '26px', dy: '-30px', rot: '10deg' },
  { left: '20%', top: '68%', size: 34, opacity: 0.7, dur: '23s', delay: '-4s', dx: '-22px', dy: '-24px', rot: '-8deg' },
  { left: '38%', top: '30%', size: 28, opacity: 0.55, dur: '17s', delay: '-8s', dx: '18px', dy: '26px', rot: '6deg' },
  { left: '52%', top: '74%', size: 40, opacity: 0.8, dur: '21s', delay: '-2s', dx: '-28px', dy: '20px', rot: '-10deg' },
  { left: '68%', top: '22%', size: 32, opacity: 0.65, dur: '25s', delay: '-6s', dx: '24px', dy: '28px', rot: '9deg' },
  { left: '82%', top: '58%', size: 48, opacity: 0.9, dur: '18s', delay: '-3s', dx: '-24px', dy: '-26px', rot: '-7deg' },
  { left: '90%', top: '32%', size: 26, opacity: 0.5, dur: '22s', delay: '-9s', dx: '20px', dy: '22px', rot: '8deg' },
  { left: '30%', top: '46%', size: 30, opacity: 0.55, dur: '20s', delay: '-5s', dx: '-18px', dy: '24px', rot: '-6deg' },
  { left: '60%', top: '46%', size: 24, opacity: 0.45, dur: '24s', delay: '-7s', dx: '22px', dy: '-20px', rot: '7deg' },
  { left: '12%', top: '44%', size: 22, opacity: 0.4, dur: '26s', delay: '-10s', dx: '16px', dy: '-18px', rot: '5deg' },
]

interface Props {
  module?: PageKey | 'login'
  /** 'ambient' sits softly behind a normal page; 'hero' is the denser,
   * higher-contrast full-screen version; 'split' is the subtler, sparser
   * take used behind the login page's left (copy) panel. */
  variant?: 'ambient' | 'hero' | 'split'
  className?: string
}

export function ThemedBackground({ module = 'dashboard', variant = 'ambient', className }: Props) {
  const icons = MODULE_ICONS[module] ?? MODULE_ICONS.login ?? [Package]
  const accent = module === 'login' ? '#4F46E5' : MODULE_ACCENTS[module as PageKey] ?? '#4F46E5'
  const isHero = variant === 'hero'
  const isSplit = variant === 'split'
  const fieldOpacity = isHero ? 1 : isSplit ? 0.55 : 0.5

  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-0 z-0 overflow-hidden ${className ?? ''}`}
    >
      {/* Aurora blobs — slow, blurred, accent-tinted depth */}
      <div
        className="animate-aurora absolute rounded-full blur-3xl"
        style={{
          left: '-10%', top: '-15%', width: '55%', height: '55%',
          background: accent, opacity: isHero ? 0.35 : 0.14, ['--aurora-dur' as string]: '26s',
        }}
      />
      <div
        className="animate-aurora absolute rounded-full blur-3xl"
        style={{
          right: '-12%', bottom: '-18%', width: '50%', height: '50%',
          background: '#8B5CF6', opacity: isHero ? 0.3 : isSplit ? 0.1 : 0.12,
          ['--aurora-dur' as string]: '32s', animationDelay: '-8s',
        }}
      />
      {isHero && (
        <div
          className="animate-aurora absolute rounded-full blur-3xl"
          style={{
            left: '40%', top: '50%', width: '40%', height: '40%',
            background: '#BF9000', opacity: 0.18,
            ['--aurora-dur' as string]: '30s', animationDelay: '-14s',
          }}
        />
      )}

      {/* Drifting field icons — 'split' shows a sparser subset so they sit
          near the edges rather than crowding a headline in the middle. */}
      {(isSplit ? SPOTS.filter((_, i) => i % 2 === 0) : SPOTS).map((s, i) => {
        const Icon = icons[i % icons.length]
        const style: CSSProperties = {
          left: s.left, top: s.top,
          opacity: s.opacity * fieldOpacity,
          color: accent,
          ['--drift-dur' as string]: s.dur,
          ['--drift-x' as string]: s.dx,
          ['--drift-y' as string]: s.dy,
          ['--drift-r' as string]: s.rot,
          animationDelay: s.delay,
        }
        return (
          <div key={i} className="animate-drift absolute" style={style}>
            <Icon size={s.size} strokeWidth={1.5} />
          </div>
        )
      })}
    </div>
  )
}
