import * as React from 'react'
import { cn } from '@/lib/utils'

function Card({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        // Glass treatment — matches Dashboard's Panel exactly, so any page
        // built on Card automatically stays in sync with it. Opacity is
        // uniform across modules with and without a photo backdrop
        // (ThemedBackground's MODULE_PHOTOS): modules without a photo just
        // show canvas + the faint aurora/icon ambient layer through it,
        // which still reads fine — no need for a second, more-opaque
        // variant just for those pages.
        'rounded-2xl border-2 border-line/80 bg-surface/28 shadow-sm dark:border-line/45 dark:bg-surface/42',
        'shadow-[inset_0_1px_0_rgba(255,255,255,0.55),0_1px_2px_rgba(16,24,40,0.04)]',
        'dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_1px_2px_rgba(0,0,0,0.25)]',
        'transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-md',
        className,
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('flex flex-col gap-1 p-6', className)} {...props} />
}

function CardTitle({ className, ...props }: React.ComponentProps<'h3'>) {
  return (
    <h3
      className={cn('font-display text-lg font-bold text-navy', className)}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<'p'>) {
  return <p className={cn('text-sm text-muted', className)} {...props} />
}

function CardContent({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('p-6 pt-0', className)} {...props} />
}

export { Card, CardHeader, CardTitle, CardDescription, CardContent }
