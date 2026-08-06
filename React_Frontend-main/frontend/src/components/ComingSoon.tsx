import type { PageKey } from '@/theme/tokens'
import { PageHeader } from './PageHeader'
import { Card, CardContent } from './ui/card'

export function ComingSoon({ title, module }: { title: string; module: PageKey }) {
  return (
    <div>
      <PageHeader title={title} subtitle="This page is being built next" module={module} />
      <Card>
        <CardContent className="flex h-48 items-center justify-center text-muted">
          {title} is coming soon.
        </CardContent>
      </Card>
    </div>
  )
}
