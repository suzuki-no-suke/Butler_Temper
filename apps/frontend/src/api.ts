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
  created_at: string
  latest_version: number | null
}

export interface BotDetail extends Bot {
  versions: Version[]
}

export interface Message {
  id: number
  seq: number
  role: 'user' | 'assistant' | 'error'
  content: string
  raw_call_id: number | null
  parts: { speaker: string; text: string }[] | null
  agent_state: Record<string, unknown> | null
  created_at: string
}

export interface Conversation {
  id: number
  bot_id: number
  bot_name: string
  bot_version: number
  title: string
  status: 'active' | 'stopped'
  agent_state: Record<string, unknown> | null
  created_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
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
  return (await res.json()) as T
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) })

export const api = {
  agents: () => request<Agent[]>('/api/agents'),
  bots: () => request<Bot[]>('/api/bots'),
  bot: (id: number) => request<BotDetail>(`/api/bots/${id}`),
  createBot: (body: { name: string; agent_id: string; settings: Settings; note: string }) =>
    post<BotDetail>('/api/bots', body),
  renameBot: (botId: number, name: string) =>
    request<BotDetail>(`/api/bots/${botId}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  createVersion: (botId: number, body: { settings: Settings; note: string }) =>
    post<Version>(`/api/bots/${botId}/versions`, body),
  conversations: (botId?: number) =>
    request<Conversation[]>(`/api/conversations${botId ? `?bot_id=${botId}` : ''}`),
  conversation: (id: number) => request<ConversationDetail>(`/api/conversations/${id}`),
  createConversation: (botId: number) =>
    post<Conversation>('/api/conversations', { bot_id: botId }),
  sendMessage: (conversationId: number, content: string) =>
    post<Message[]>(`/api/conversations/${conversationId}/messages`, { content }),
}
