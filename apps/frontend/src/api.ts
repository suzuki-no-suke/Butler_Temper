// Backend（FastAPI）との通信

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export type Settings = Record<string, unknown>

export interface Version {
  id: number
  version: number
  settings: Settings
  note: string
  created_at: string
}

export interface Agent {
  id: string
  name: string
  description: string
  models: Record<string, string>
  default_settings: Settings
}

export interface Bot {
  id: number
  name: string
  agent_id: string
  agent_name: string
  unavailable_reason: string | null
  forked_from_bot_id: number | null
  forked_from_bot_name: string | null
  forked_from_version: number | null
  created_at: string
  latest_version: number | null
}

export interface BotDetail extends Bot {
  versions: Version[]
}

export type Rating = 'GOOD' | 'FINE' | 'BAD'
export const RATINGS: Rating[] = ['GOOD', 'FINE', 'BAD']

export interface MessageComment {
  rating: Rating
  text: string
  updated_at: string
}

export interface ConversationComment {
  id: number
  rating: Rating | null
  text: string
  created_at: string
}

export interface ConversationSettings {
  bot_id: number
  bot_name: string
  agent_id: string
  agent_name: string
  version: number
  note: string
  created_at: string
  settings: Settings
}

export interface SettingsChatMessage {
  id: number
  role: 'user' | 'assistant' | 'error'
  content: string
  proposed_settings: Settings | null
  created_at: string
}

export interface RawExchange {
  label?: string
  method?: string
  url?: string
  status?: number
  sent_at?: string
  received_at?: string
  request_headers?: Record<string, string>
  response_headers?: Record<string, string>
  request?: unknown
  response?: unknown
}

export interface RawCall {
  id: number
  conversation_id: number | null
  agent_id: string
  source_hash: string
  exchanges: RawExchange[]
  error: string | null
  started_at: string
  finished_at: string | null
}

export interface Message {
  id: number
  seq: number
  role: 'user' | 'assistant' | 'error'
  content: string
  raw_call_id: number | null
  parts: { speaker: string; text: string; secret?: string }[] | null
  agent_state: Record<string, unknown> | null
  created_at: string
  comment: MessageComment | null
}

export interface Conversation {
  id: number
  bot_id: number
  bot_name: string
  bot_version: number
  title: string
  status: 'active' | 'stopped'
  agent_state: Record<string, unknown> | null
  resumed_from_id: number | null
  created_at: string
  message_count: number
  preview: string
  last_message_at: string | null
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
  comments: ConversationComment[]
}

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (body.detail !== undefined) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      // 本文が JSON でなければステータスだけを出す
    }
    throw new ApiError(detail)
  }
  const text = await res.text()
  return (text === '' ? null : JSON.parse(text)) as T
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) })

export const api = {
  agents: () => request<Agent[]>('/api/agents'),
  bots: () => request<Bot[]>('/api/bots'),
  bot: (id: number) => request<BotDetail>(`/api/bots/${id}`),
  createBot: (body: { name: string; agent_id: string; settings: Settings; note: string }) =>
    post<BotDetail>('/api/bots', body),
  forkBot: (
    botId: number,
    body: { name: string; settings: Settings; note: string; base_version: number | null },
  ) => post<BotDetail>(`/api/bots/${botId}/fork`, body),
  createVersion: (botId: number, body: { settings: Settings; note: string }) =>
    post<Version>(`/api/bots/${botId}/versions`, body),
  conversations: (botId?: number) =>
    request<Conversation[]>(`/api/conversations${botId ? `?bot_id=${botId}` : ''}`),
  conversation: (id: number) => request<ConversationDetail>(`/api/conversations/${id}`),
  createConversation: (botId: number) =>
    post<Conversation>('/api/conversations', { bot_id: botId }),
  resumeConversation: (id: number) => post<Conversation>(`/api/conversations/${id}/resume`, {}),
  sendMessage: (conversationId: number, content: string) =>
    post<Message[]>(`/api/conversations/${conversationId}/messages`, { content }),
  rawCall: (id: number) => request<RawCall>(`/api/raw-calls/${id}`),
  conversationSettings: (id: number) =>
    request<ConversationSettings>(`/api/conversations/${id}/settings`),
  putMessageComment: (messageId: number, rating: Rating, text: string) =>
    request<MessageComment>(`/api/messages/${messageId}/comment`, {
      method: 'PUT',
      body: JSON.stringify({ rating, text }),
    }),
  deleteMessageComment: (messageId: number) =>
    request<null>(`/api/messages/${messageId}/comment`, { method: 'DELETE' }),
  addConversationComment: (conversationId: number, rating: Rating | null, text: string) =>
    post<ConversationComment>(`/api/conversations/${conversationId}/comments`, { rating, text }),
  deleteConversationComment: (commentId: number) =>
    request<null>(`/api/conversation-comments/${commentId}`, { method: 'DELETE' }),
  settingsChat: (botId: number) =>
    request<SettingsChatMessage[]>(`/api/bots/${botId}/settings-chat`),
  sendSettingsChat: (botId: number, message: string, currentSettings: string) =>
    post<{ messages: SettingsChatMessage[]; proposed_settings: Settings | null }>(
      `/api/bots/${botId}/settings-chat`,
      { message, current_settings: currentSettings },
    ),
  clearSettingsChat: (botId: number) =>
    request<null>(`/api/bots/${botId}/settings-chat`, { method: 'DELETE' }),
}
