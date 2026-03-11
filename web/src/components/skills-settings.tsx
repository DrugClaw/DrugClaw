import React, { useEffect, useMemo, useState } from 'react'
import { Button, Card, Flex, Text, Switch, Badge, Callout, Select } from '@radix-ui/themes'
import { api } from '../lib/api'
import { ConfigFieldCard } from './config-field-card'

type SkillStatus = {
  name: string
  description: string
  enabled: boolean
  source: string
  version?: string
  platforms: string[]
  reason?: string
}

type SkillsResponse = {
  ok: boolean
  skills: SkillStatus[]
}

export function SkillsSettings() {
  const [skills, setSkills] = useState<SkillStatus[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(5)

  const loadSkills = async () => {
    setLoading(true)
    try {
      const res = await api<SkillsResponse>('/api/skills')
      setSkills(res.skills)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadSkills()
  }, [])

  const toggleSkill = async (name: string, currentEnabled: boolean) => {
    try {
      const action = currentEnabled ? 'disable' : 'enable'
      await api(`/api/skills/${name}/${action}`, { method: 'POST' })
      await loadSkills()
    } catch (e) {
      setError(`Failed to ${currentEnabled ? 'disable' : 'enable'} ${name}: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  // Client-side pagination
  const totalPages = Math.max(1, Math.ceil(skills.length / pageSize))
  const currentPage = Math.min(page, totalPages)
  const pagedSkills = useMemo(() => {
    const start = (currentPage - 1) * pageSize
    return skills.slice(start, start + pageSize)
  }, [skills, currentPage, pageSize])

  return (
    <div className="flex flex-col gap-4 h-full">
      {error && (
        <Callout.Root color="red" size="1" variant="soft">
          <Callout.Text>{error}</Callout.Text>
        </Callout.Root>
      )}

      <ConfigFieldCard
        label="Installed Skills"
        description="Manage skills installed in your DrugClaw runtime. Toggling a skill applies changes immediately."
      >

        <div className="flex flex-col gap-2 mt-2">
          {loading && <Text size="1" color="gray">Loading skills...</Text>}
          {!loading && skills.length === 0 && <Text size="1" color="gray">No skills installed.</Text>}
          {pagedSkills.map((skill) => (
            <Card key={skill.name} variant="surface" className="p-3">
              <Flex justify="between" align="center">
                <Flex direction="column" gap="1" style={{ flex: 1 }}>
                  <Flex align="center" gap="2">
                    <Text weight="bold" size="2">{skill.name}</Text>
                    {skill.version && <Badge size="1" color="gray">v{skill.version}</Badge>}
                    {skill.source !== 'local' && <Badge size="1" color="blue">{skill.source}</Badge>}
                    {!skill.enabled && skill.reason && (
                      <Badge size="1" color="orange" title={skill.reason}>Unavailable</Badge>
                    )}
                  </Flex>
                  <Text size="1" color="gray" style={{
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical' as any,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>{skill.description}</Text>
                </Flex>
                <Flex align="center" gap="3">
                  <Switch
                    checked={skill.enabled}
                    onCheckedChange={() => toggleSkill(skill.name, skill.enabled)}
                  />
                </Flex>
              </Flex>
            </Card>
          ))}
          {skills.length > 0 && (
            <Flex align="center" justify="between" className="mt-2">
              <Flex align="center" gap="2">
                <Text size="1" color="gray">Page size</Text>
                <Select.Root value={String(pageSize)} onValueChange={(v) => { setPage(1); setPageSize(parseInt(v, 10) || 5) }}>
                  <Select.Trigger variant="surface" />
                  <Select.Content>
                    <Select.Item value="5">5</Select.Item>
                    <Select.Item value="10">10</Select.Item>
                    <Select.Item value="20">20</Select.Item>
                    <Select.Item value="50">50</Select.Item>
                  </Select.Content>
                </Select.Root>
              </Flex>

              <Flex gap="3" align="center">
                <Text size="1" color="gray">Page {currentPage} / {totalPages}</Text>
                <Flex gap="2">
                  <Button size="1" variant="soft" disabled={currentPage <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>Prev</Button>
                  <Button size="1" variant="soft" disabled={currentPage >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Next</Button>
                </Flex>
              </Flex>
            </Flex>
          )}
        </div>
      </ConfigFieldCard>

    </div>
  )
}
