import {
  Truck, Plane, Warehouse, ShoppingCart, Container, Globe,
  ClipboardList, BarChart3, MessageSquare, Gauge, Users,
  type LucideIcon,
} from 'lucide-react'
import type { PageKey } from '@/theme/tokens'
import { MODULE_ACCENTS } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import { cn } from '@/lib/utils'
import heroLight from '@/assets/dashboard-hero-light.png'
import heroDark from '@/assets/dashboard-hero-dark.png'

/**
 * Ambient, subject-related backdrop: a slow, soft "smoke" of blurred,
 * accent-tinted aurora blobs, with a single large, static watermark icon
 * for the module (truck for Logistics, warehouse for Inventory, plane for
 * Imports, ...) anchored quietly in a back corner. Deliberately calm — one
 * still motif instead of a field of drifting icons — so every tab reads as
 * its own coherent mood instead of something competing with the content on
 * top of it.
 *
 * CSS-only motion for the smoke (see index.css `aurora` keyframes) — the
 * safe, reliable path here. The watermark icon itself never animates.
 */

const MODULE_ICON: Partial<Record<PageKey | 'login', LucideIcon>> = {
  dashboard: Gauge,
  purchases: ShoppingCart,
  inventory: Warehouse,
  imports: Plane,
  importsStatus: Container,
  logisticsStatus: Truck,
  dataEntry: ClipboardList,
  logistics: Truck,
  reports: BarChart3,
  assistant: MessageSquare,
  userManagement: Users,
  login: Globe,
}

function DashboardPhoto({ className }: { className?: string }) {
  const { dark } = useTheme()
  return (
    <div aria-hidden className={cn('pointer-events-none absolute inset-0 z-0 overflow-hidden', className)}>
      <img src={dark ? heroDark : heroLight} alt="" className="h-full w-full object-cover" />
      {/* Light scrim so cards can go semi-transparent anywhere on the page
          and still keep their text readable over busy parts of the photo. */}
      <div className="absolute inset-0" style={{ background: dark ? 'rgba(11,14,20,0.4)' : 'rgba(255,255,255,0.3)' }} />
    </div>
  )
}

interface Props {
  module?: PageKey | 'login'
  /** 'ambient' sits softly behind a normal page; 'hero' is the denser,
   * higher-contrast full-screen version; 'split' is the subtler, sparser
   * take used behind the login page's left (copy) panel. */
  variant?: 'ambient' | 'hero' | 'split'
  className?: string
}

export function ThemedBackground({ module = 'dashboard', variant = 'ambient', className }: Props) {
  // Dashboard is the flagship: a real port/logistics photo fills the whole
  // page behind the (semi-transparent) cards, instead of a per-module icon.
  // It's a single static <img> — no blur/animation — so it costs one paint,
  // not a per-frame one.
  if (module === 'dashboard') return <DashboardPhoto className={className} />

  const Icon = MODULE_ICON[module] ?? Globe
  const accent = module === 'login' ? '#4F46E5' : MODULE_ACCENTS[module as PageKey] ?? '#4F46E5'
  const isHero = variant === 'hero'
  const isSplit = variant === 'split'

  return (
    <div
      aria-hidden
      className={cn('pointer-events-none absolute inset-0 z-0 overflow-hidden', className)}
    >
      {/* Smoky aurora blobs — slow, blurred, accent-tinted depth */}
      <div
        className="animate-aurora absolute rounded-full blur-3xl"
        style={{
          left: '-10%', top: '-15%', width: '55%', height: '55%',
          background: accent, opacity: isHero ? 0.3 : 0.12, ['--aurora-dur' as string]: '30s',
        }}
      />
      <div
        className="animate-aurora absolute rounded-full blur-3xl"
        style={{
          right: '-12%', bottom: '-18%', width: '50%', height: '50%',
          background: '#8B5CF6', opacity: isHero ? 0.24 : isSplit ? 0.08 : 0.1,
          ['--aurora-dur' as string]: '36s', animationDelay: '-10s',
        }}
      />
      {isHero && (
        <div
          className="animate-aurora absolute rounded-full blur-3xl"
          style={{
            left: '35%', top: '45%', width: '40%', height: '40%',
            background: '#BF9000', opacity: 0.14,
            ['--aurora-dur' as string]: '34s', animationDelay: '-16s',
          }}
        />
      )}

      {/* Single large, static watermark motif — the module's identity,
          anchored top-right so it sits in the open header band every page
          has above its first card row, instead of a bottom corner that a
          dense content grid always ends up covering entirely. */}
      <Icon
        size={isHero ? 460 : isSplit ? 420 : 340}
        strokeWidth={1}
        className="absolute"
        style={{
          right: isSplit ? '-10%' : '-4%',
          top: isHero ? '-12%' : isSplit ? '-8%' : '-10%',
          color: accent,
          opacity: isHero ? 0.22 : isSplit ? 0.12 : 0.16,
          transform: 'rotate(8deg)',
        }}
      />
    </div>
  )
}
