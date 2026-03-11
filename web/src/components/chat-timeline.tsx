import React from 'react'
import { Badge, Card, Flex, Text } from '@radix-ui/themes'
import { StickToBottom } from 'use-stick-to-bottom'
import { cn } from '../lib/utils'
import { messageBubbleVariants } from '../lib/ui'
import { MessageMarkdown } from './message-markdown'
import type { MessageItem } from '../types'

type ChatTimelineProps = {
  messages: MessageItem[]
}

export function ChatTimeline({ messages }: ChatTimelineProps) {
  return (
    <div className="min-h-0 flex-1">
      <StickToBottom className="relative h-full overflow-y-auto" resize="smooth" initial="smooth">
        <StickToBottom.Content className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-3 py-4 md:px-6">
          {messages.map((m) => (
            <div
              key={m.id}
              className={cn('flex w-full', m.is_from_bot ? 'justify-start' : 'justify-end')}
            >
              <Card className={messageBubbleVariants({ role: m.is_from_bot ? 'bot' : 'user' })}>
                <Flex justify="between" align="center" gap="2">
                  <Badge color={m.is_from_bot ? 'teal' : 'gray'} variant="soft">
                    {m.sender_name}
                  </Badge>
                  <Text size="1" color="gray">
                    {new Date(m.timestamp).toLocaleTimeString()}
                  </Text>
                </Flex>
                <MessageMarkdown content={m.content} />
              </Card>
            </div>
          ))}
        </StickToBottom.Content>
      </StickToBottom>
    </div>
  )
}
