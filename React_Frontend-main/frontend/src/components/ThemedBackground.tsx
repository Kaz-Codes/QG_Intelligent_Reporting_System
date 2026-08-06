import {
  Truck, Plane, Warehouse, ShoppingCart, Container, Globe, Route,
  ClipboardList, BarChart3, MessageSquare, Gauge, Users,
  type LucideIcon,
} from 'lucide-react'
import type { PageKey } from '@/theme/tokens'
import { MODULE_ACCENTS } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import { cn } from '@/lib/utils'
import dashboardLight from '@/assets/dashboard-hero-light.png'
import dashboardDark from '@/assets/dashboard-hero-dark.png'
import logisticsLight from '@/assets/logistics-hero-light.png'
import logisticsDark from '@/assets/logistics-hero-dark.png'
import importsLight from '@/assets/imports-hero-light.png'
import importsDark from '@/assets/imports-hero-dark.png'
import purchasesLight from '@/assets/purchases-hero-light.png'
import purchasesDark from '@/assets/purchases-hero-dark.png'
import inventoryLight from '@/assets/inventory-hero-light.png'
import inventoryDark from '@/assets/inventory-hero-dark.png'
import loginLight from '@/assets/login-hero-light.png'
import loginDark from '@/assets/login-hero-dark.png'

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
 *
 * A module can instead be given a real photo (see MODULE_PHOTOS below) —
 * that replaces the icon+aurora treatment entirely for that module, the
 * same way Dashboard's port/logistics photo always has.
 */

const MODULE_ICON: Partial<Record<PageKey | 'login', LucideIcon>> = {
  dashboard: Gauge,
  purchases: ShoppingCart,
  inventory: Warehouse,
  imports: Plane,
  importsStatus: Container,
  logisticsStatus: Truck,
  truckingStatus: Route,
  dataEntry: ClipboardList,
  logistics: Truck,
  reports: BarChart3,
  assistant: MessageSquare,
  userManagement: Users,
  login: Globe,
}

interface ModulePhotoSet {
  light: string
  dark: string
  /** Scrim strength override (0-1). Pages built from many small,
   * text-dense cards (filters, KPI grids, tables) need a stronger wash
   * than Login's couple of large cards do — their bright/busy photo
   * detail was bleeding through the low-opacity Card surface enough to
   * hurt readability. Defaults to the original light 0.3 / dark 0.4. */
  scrim?: { light: number; dark: number }
  /** Mutes the photo itself (desaturated, slightly dimmed) instead of
   * just washing it harder — makes it read as a quiet backdrop rather
   * than something competing for attention with the cards on top. */
  dull?: boolean
}

// Scrim = how much wash sits over the photo, so higher means the photo shows
// through less. Raised ~0.10 across the module backdrops to push them further
// behind the content — the numbers are the thing being read, the photo is
// only setting the mood. Login is deliberately untouched: it has no data on
// top of it, so its photo can stay at full strength.
const DENSE_SCRIM = { light: 0.74, dark: 0.68 }
const DULL_FILTER = 'saturate(0.65) brightness(0.94) contrast(0.97)'

/** Modules with a real photo instead of the icon+aurora treatment.
 * Add an entry here (plus a light/dark import above) to give another
 * module the same "photo behind glass cards" look Dashboard and
 * Logistics have. */
const MODULE_PHOTOS: Partial<Record<PageKey | 'login', ModulePhotoSet>> = {
  dashboard: { light: dashboardLight, dark: dashboardDark, scrim: { light: 0.46, dark: 0.52 }, dull: true },
  logistics: { light: logisticsLight, dark: logisticsDark, scrim: DENSE_SCRIM, dull: true },
  imports: { light: importsLight, dark: importsDark, scrim: DENSE_SCRIM, dull: true },
  purchases: { light: purchasesLight, dark: purchasesDark, scrim: DENSE_SCRIM, dull: true },
  inventory: { light: inventoryLight, dark: inventoryDark, scrim: DENSE_SCRIM, dull: true },
  login: { light: loginLight, dark: loginDark },
}

function ModulePhoto({ photo, className }: { photo: ModulePhotoSet; className?: string }) {
  const { dark } = useTheme()
  const scrimOpacity = dark ? (photo.scrim?.dark ?? 0.4) : (photo.scrim?.light ?? 0.3)
  return (
    <div aria-hidden className={cn('pointer-events-none absolute inset-0 z-0 overflow-hidden', className)}>
      <img
        src={dark ? photo.dark : photo.light}
        alt=""
        className="h-full w-full object-cover"
        style={photo.dull ? { filter: DULL_FILTER } : undefined}
      />
      {/* Scrim so cards can go semi-transparent anywhere on the page and
          still keep their text readable over busy parts of the photo. */}
      <div
        className="absolute inset-0"
        style={{ background: dark ? `rgba(11,14,20,${scrimOpacity})` : `rgba(255,255,255,${scrimOpacity})` }}
      />
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
  // A real photo fills the whole page behind the (semi-transparent) cards,
  // instead of a per-module icon, for any module listed in MODULE_PHOTOS.
  // It's a single static <img> — no blur/animation — so it costs one
  // paint, not a per-frame one.
  const photo = MODULE_PHOTOS[module]
  if (photo) return <ModulePhoto photo={photo} className={className} />

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
