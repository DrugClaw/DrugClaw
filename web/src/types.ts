export type SessionItem = {
  session_key: string
  label: string
  chat_id: number
  chat_type: string
  last_message_time?: string
  last_message_preview?: string | null
}

export type MessageItem = {
  id: string
  sender_name: string
  content: string
  is_from_bot: boolean
  timestamp: string
}
