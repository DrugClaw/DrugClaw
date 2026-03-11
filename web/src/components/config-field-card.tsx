import React from 'react'
import { Card, Text } from '@radix-ui/themes'

export type ConfigFieldCardProps = {
  label: string
  description: React.ReactNode
  children: React.ReactNode
}

export function ConfigFieldCard({ label, description, children }: ConfigFieldCardProps) {
  return (
    <Card className="p-3">
      <Text size="2" weight="medium">{label}</Text>
      <Text size="1" color="gray" className="mt-1 block">{description}</Text>
      <div className="mt-2">{children}</div>
    </Card>
  )
}
