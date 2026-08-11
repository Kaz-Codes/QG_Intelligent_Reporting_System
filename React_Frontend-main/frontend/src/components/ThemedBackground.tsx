import {
  Truck, Plane, Warehouse, ShoppingCart, Container, Globe, Route,
  ClipboardList, BarChart3, MessageSquare, Gauge, Users,
  type LucideIcon,
} from 'lucide-react'
import type { PageKey } from '@/theme/tokens'
import { MODULE_ACCENTS, BRAND, VIOLET, GOLD } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import { cn } from '@/lib/utils'
import dashboardLight from '@/assets/dashboard-hero-light.webp'
import dashboardDark from '@/assets/dashboard-hero-dark.webp'
import logisticsLight from '@/assets/logistics-hero-light.webp'
import logisticsDark from '@/assets/logistics-hero-dark.webp'
import importsLight from '@/assets/imports-hero-light.webp'
import importsDark from '@/assets/imports-hero-dark.webp'
import purchasesLight from '@/assets/purchases-hero-light.webp'
import purchasesDark from '@/assets/purchases-hero-dark.webp'
import inventoryLight from '@/assets/inventory-hero-light.webp'
import inventoryDark from '@/assets/inventory-hero-dark.webp'
import loginLight from '@/assets/login-hero-light.webp'
import loginDark from '@/assets/login-hero-dark.webp'
import assistantLight from '@/assets/assistant-hero-light.webp'
import assistantDark from '@/assets/assistant-hero-dark.webp'

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
//
// This used to be pinned at 0.82 to keep secondary text legible: with the old
// translucent Card (bg-surface/40) and the old lighter `muted` (#5A6478), a
// 0.74 wash measured 4.24:1 over the darkest parts of these photos, i.e. below
// WCAG AA. The enterprise restyle removed that constraint from both ends —
// Card is now /78 · /82 and `muted` darkened to #475569 — so the photo barely
// reaches the text at all. Re-measured against the real images, the worst case
// across all five modules is now 6.23:1 in light and 7.13:1 in dark even at the
// LIGHTEST scrim in use, so these values are free to be a design choice again.
// Still worth re-measuring if Card ever goes translucent again.
const DENSE_SCRIM = { light: 0.80, dark: 0.76 }
const DULL_FILTER = 'saturate(0.65) brightness(0.94) contrast(0.97)'

/** Modules with a real photo instead of the icon+aurora treatment.
 * Add an entry here (plus a light/dark import above) to give another
 * module the same "photo behind glass cards" look Dashboard and
 * Logistics have. */
const MODULE_PHOTOS: Partial<Record<PageKey | 'login', ModulePhotoSet>> = {
  // Dashboard keeps a lighter wash than the rest so its photo stays visible
  // behind the overview. That was a contrast problem at the old 0.46 (secondary
  // text measured 3.04:1); at 0.58, against the restyle's opaque Card and
  // darker `muted`, it measures 6.35:1 — comfortably legible.
  dashboard: { light: dashboardLight, dark: dashboardDark, scrim: { light: 0.58, dark: 0.62 }, dull: true },
  logistics: { light: logisticsLight, dark: logisticsDark, scrim: DENSE_SCRIM, dull: true },
  imports: { light: importsLight, dark: importsDark, scrim: DENSE_SCRIM, dull: true },
  purchases: { light: purchasesLight, dark: purchasesDark, scrim: DENSE_SCRIM, dull: true },
  inventory: { light: inventoryLight, dark: inventoryDark, scrim: DENSE_SCRIM, dull: true },
  login: { light: loginLight, dark: loginDark },
  // Chat history is as text-dense as any of the module dashboards once a
  // conversation is underway, so this doesn't get login's full-strength
  // treatment — but the source photos are already heavily pre-faded
  // (unlike the other modules' saturated originals), so DENSE_SCRIM's 0.80
  // white wash in light mode compounded into "not visible" (reported by
  // design review). Scrim is tuned down instead of reusing DENSE_SCRIM, and
  // `dull` is skipped since the photo has no vibrance left to tone down.
  assistant: { light: assistantLight, dark: assistantDark, scrim: { light: 0.32, dark: 0.76 } },
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
  const accent = module === 'login' ? BRAND : MODULE_ACCENTS[module as PageKey] ?? BRAND
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
          background: VIOLET, opacity: isHero ? 0.24 : isSplit ? 0.08 : 0.1,
          ['--aurora-dur' as string]: '36s', animationDelay: '-10s',
        }}
      />
      {isHero && (
        <div
          className="animate-aurora absolute rounded-full blur-3xl"
          style={{
            left: '35%', top: '45%', width: '40%', height: '40%',
            background: GOLD, opacity: 0.14,
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
