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
  // 割込み要求を伝えられる相手。空なら割込みを受け付けない
  interrupt_targets: string[]
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
  dialogue_id: number | null
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

export interface BotApi {
  agents: () => Promise<Agent[]>
  bots: () => Promise<Bot[]>
  bot: (id: number) => Promise<BotDetail>
  createBot: (body: { name: string; agent_id: string; settings: Settings; note: string }) => Promise<BotDetail>
  forkBot: (
    botId: number,
    body: { name: string; settings: Settings; note: string; base_version: number | null },
  ) => Promise<BotDetail>
  createVersion: (botId: number, body: { settings: Settings; note: string }) => Promise<Version>
  settingsChat: (botId: number) => Promise<SettingsChatMessage[]>
  sendSettingsChat: (
    botId: number,
    message: string,
    currentSettings: string,
  ) => Promise<{ messages: SettingsChatMessage[]; proposed_settings: Settings | null }>
  clearSettingsChat: (botId: number) => Promise<null>
}

// Agent と会話用エージェントは、同じ形の API を別の場所に持つ
const botApi = (agentsPath: string, botsPath: string): BotApi => ({
  agents: () => request<Agent[]>(agentsPath),
  bots: () => request<Bot[]>(botsPath),
  bot: (id) => request<BotDetail>(`${botsPath}/${id}`),
  createBot: (body) => post<BotDetail>(botsPath, body),
  forkBot: (botId, body) => post<BotDetail>(`${botsPath}/${botId}/fork`, body),
  createVersion: (botId, body) => post<Version>(`${botsPath}/${botId}/versions`, body),
  settingsChat: (botId) => request<SettingsChatMessage[]>(`${botsPath}/${botId}/settings-chat`),
  sendSettingsChat: (botId, message, currentSettings) =>
    post(`${botsPath}/${botId}/settings-chat`, { message, current_settings: currentSettings }),
  clearSettingsChat: (botId) =>
    request<null>(`${botsPath}/${botId}/settings-chat`, { method: 'DELETE' }),
})

export const agentBotApi = botApi('/api/agents', '/api/bots')
export const conversationBotApi = botApi('/api/conversation-agents', '/api/conversation-bots')

// 発言への評価・コメントと、会話全体へのコメント
export interface CommentApi {
  putMessageComment: (messageId: number, rating: Rating, text: string) => Promise<MessageComment>
  deleteMessageComment: (messageId: number) => Promise<null>
  addComment: (ownerId: number, rating: Rating | null, text: string) => Promise<ConversationComment>
  deleteComment: (commentId: number) => Promise<null>
}

const commentApi = (messagesPath: string, ownersPath: string, commentsPath: string): CommentApi => ({
  putMessageComment: (messageId, rating, text) =>
    request<MessageComment>(`${messagesPath}/${messageId}/comment`, {
      method: 'PUT',
      body: JSON.stringify({ rating, text }),
    }),
  deleteMessageComment: (messageId) =>
    request<null>(`${messagesPath}/${messageId}/comment`, { method: 'DELETE' }),
  addComment: (ownerId, rating, text) =>
    post<ConversationComment>(`${ownersPath}/${ownerId}/comments`, { rating, text }),
  deleteComment: (commentId) => request<null>(`${commentsPath}/${commentId}`, { method: 'DELETE' }),
})

export const conversationCommentApi = commentApi(
  '/api/messages',
  '/api/conversations',
  '/api/conversation-comments',
)
export const dialogueCommentApi = commentApi(
  '/api/dialogue-messages',
  '/api/dialogues',
  '/api/dialogue-comments',
)

export interface TemplateVersion {
  id: number
  version: number
  content: string
  note: string
  created_at: string
}

export interface Template {
  id: number
  name: string
  created_at: string
  latest_version: number
}

export interface TemplateDetail extends Template {
  versions: TemplateVersion[]
}

export interface DialogueMessage {
  id: number
  seq: number
  // conversation（会話用エージェント）/ agent（Agent）
  speaker: 'conversation' | 'agent'
  role: 'speech' | 'error'
  content: string
  raw_call_id: number | null
  parts: { speaker: string; text: string; secret?: string }[] | null
  agent_state: Record<string, unknown> | null
  created_at: string
  comment: MessageComment | null
}

export interface DialogueTemplate {
  name: string
  template_id: number
  version: number
}

export interface Dialogue {
  id: number
  conversation_bot_id: number
  conversation_bot_name: string
  conversation_bot_version: number
  bot_id: number
  bot_name: string
  bot_version: number
  templates: DialogueTemplate[]
  status: 'active' | 'stopped'
  resumed_from_id: number | null
  created_at: string
  message_count: number
  preview: string
  last_message_at: string | null
}

export interface DialogueDetail extends Dialogue {
  messages: DialogueMessage[]
  comments: ConversationComment[]
}

export interface DialogueSettings {
  conversation_bot: ConversationSettings
  bot: ConversationSettings
  templates: (DialogueTemplate & { content: string })[]
}

export const api = {
  ...agentBotApi,
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
  templates: () => request<Template[]>('/api/templates'),
  template: (id: number) => request<TemplateDetail>(`/api/templates/${id}`),
  createTemplate: (body: { name: string; content: string; note: string }) =>
    post<TemplateDetail>('/api/templates', body),
  createTemplateVersion: (templateId: number, body: { content: string; note: string }) =>
    post<TemplateVersion>(`/api/templates/${templateId}/versions`, body),
  dialogues: (filter: { conversationBotId?: number; botId?: number } = {}) => {
    const params = new URLSearchParams()
    if (filter.conversationBotId) params.set('conversation_bot_id', String(filter.conversationBotId))
    if (filter.botId) params.set('bot_id', String(filter.botId))
    const query = params.toString()
    return request<Dialogue[]>(`/api/dialogues${query ? `?${query}` : ''}`)
  },
  dialogue: (id: number) => request<DialogueDetail>(`/api/dialogues/${id}`),
  createDialogue: (conversationBotId: number, botId: number) =>
    post<Dialogue>('/api/dialogues', { conversation_bot_id: conversationBotId, bot_id: botId }),
  advanceDialogue: (id: number) => post<DialogueMessage[]>(`/api/dialogues/${id}/turn`, {}),
  resumeDialogue: (id: number) => post<Dialogue>(`/api/dialogues/${id}/resume`, {}),
  dialogueSettings: (id: number) => request<DialogueSettings>(`/api/dialogues/${id}/settings`),
}
