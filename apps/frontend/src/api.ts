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

export interface AgentTemplateUsed {
  name: string
  template_id: number
  version: number
  content: string
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
  // 開始時に固定した Agent テンプレートと、それを埋め込んだ設定。仕組みより前の記録では空と null
  agent_templates: AgentTemplateUsed[]
  resolved_settings: Settings | null
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
  parallel_candidate_id: number | null
  agent_id: string
  source_hash: string
  exchanges: RawExchange[]
  error: string | null
  started_at: string
  finished_at: string | null
}

// 表示用の内訳。speaker が simulation なら、シミュレータの呼び出しと結果（中身は実行記録にある）
export interface MessagePart {
  speaker: string
  text: string
  secret?: string
  simulation_run_id?: number | null
}

export interface Message {
  id: number
  seq: number
  role: 'user' | 'assistant' | 'error'
  content: string
  raw_call_id: number | null
  parts: MessagePart[] | null
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
  // 並行会話の候補を採用して作った会話なら、その候補と並行会話
  parallel_candidate_id: number | null
  parallel_conversation_id: number | null
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
  parts: MessagePart[] | null
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

export interface SimulatorParam {
  name: string
  // required（必須）/ optional（任意）/ global（指定不可。グローバル設定でのみ決める）
  kind: 'required' | 'optional' | 'global'
  description: string
  global_key: string | null
  // 任意の項目の既定値（グローバル設定から取るものは、今の設定の値）
  default: unknown
}

export interface SimulatorProposal {
  reply: string
  // 既定値の項目も含めた引数の全体。提案しない場合は null
  args: Record<string, unknown> | null
}

export interface Simulator {
  name: string
  label: string
  description: string
  result_description: string
  input_schema: Record<string, unknown>
  params: SimulatorParam[]
}

export type SimulationCaller = 'conversation' | 'dialogue' | 'webui' | 'parallel'

export interface SimulationRun {
  id: number
  simulator: string
  caller: SimulationCaller
  conversation_id: number | null
  message_id: number | null
  dialogue_id: number | null
  dialogue_message_id: number | null
  parallel_candidate_id: number | null
  agent_id: string
  args: Record<string, unknown>
  params: Record<string, unknown> | null
  status: 'succeeded' | 'failed' | 'invalid'
  result: Record<string, unknown> | null
  detail: Record<string, unknown> | null
  error_count: number
  error: string | null
  started_at: string
  finished_at: string | null
}

export interface SimulationRawCall {
  id: number
  label: string
  exchanges: RawExchange[]
  error: string | null
  created_at: string
}

export interface SimulationRunDetail extends SimulationRun {
  raw_calls: SimulationRawCall[]
}

export interface SimulationSettings {
  values: Record<string, unknown>
  defaults: Record<string, unknown>
  descriptions: Record<string, string>
}

// 並行会話の候補一つ（Agent の 1 ターン分の結果）
export interface ParallelCandidate {
  id: number
  index: number
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  text: string | null
  parts: MessagePart[] | null
  agent_state: Record<string, unknown> | null
  error: string | null
  raw_call_id: number | null
  created_at: string
  finished_at: string | null
  // この候補を採用して作った会話
  conversation_ids: number[]
}

// 一つの入力に対して候補を作った 1 回分
export interface ParallelRound {
  id: number
  content: string
  count: number
  created_at: string
  candidates: ParallelCandidate[]
}

export interface ParallelConversation {
  id: number
  bot_id: number
  bot_name: string
  bot_version: number
  // 写した元: conversation（チャットの会話）/ dialogue（エージェント間対話）/ new（会話の最初から）
  source_kind: 'conversation' | 'dialogue' | 'new'
  created_at: string
  message_count: number
  round_count: number
  preview: string
}

export interface ParallelConversationDetail extends ParallelConversation {
  messages: Message[]
  rounds: ParallelRound[]
}

export interface ParallelSettings {
  concurrency: number
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
  agentTemplates: () => request<Template[]>('/api/agent-templates'),
  agentTemplate: (id: number) => request<TemplateDetail>(`/api/agent-templates/${id}`),
  createAgentTemplate: (body: { name: string; content: string; note: string }) =>
    post<TemplateDetail>('/api/agent-templates', body),
  createAgentTemplateVersion: (templateId: number, body: { content: string; note: string }) =>
    post<TemplateVersion>(`/api/agent-templates/${templateId}/versions`, body),
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
  simulators: () => request<Simulator[]>('/api/simulators'),
  testRunSimulator: (name: string, args: Record<string, unknown>, times: number) =>
    post<SimulationRun[]>(`/api/simulators/${name}/runs`, { args, times }),
  proposeSimulatorArgs: (
    name: string,
    body: { request: string; history: { role: string; content: string }[]; current_args: string },
  ) => post<SimulatorProposal>(`/api/simulators/${name}/propose`, body),
  simulationRuns: (filter: { simulator?: string; caller?: string } = {}) => {
    const params = new URLSearchParams()
    if (filter.simulator) params.set('simulator', filter.simulator)
    if (filter.caller) params.set('caller', filter.caller)
    const query = params.toString()
    return request<SimulationRun[]>(`/api/simulation-runs${query ? `?${query}` : ''}`)
  },
  simulationRun: (id: number) => request<SimulationRunDetail>(`/api/simulation-runs/${id}`),
  simulationSettings: () => request<SimulationSettings>('/api/simulation-settings'),
  startParallelFromConversation: (conversationId: number, messageId: number) =>
    post<ParallelConversation>(`/api/conversations/${conversationId}/parallel`, {
      message_id: messageId,
    }),
  startParallelFromDialogue: (dialogueId: number, messageId: number) =>
    post<ParallelConversation>(`/api/dialogues/${dialogueId}/parallel`, { message_id: messageId }),
  startParallelNew: (botId: number) =>
    post<ParallelConversation>('/api/parallel-conversations', { bot_id: botId }),
  parallelConversations: () => request<ParallelConversation[]>('/api/parallel-conversations'),
  parallelConversation: (id: number) =>
    request<ParallelConversationDetail>(`/api/parallel-conversations/${id}`),
  createParallelRound: (id: number, content: string, count: number) =>
    post<ParallelRound>(`/api/parallel-conversations/${id}/rounds`, { content, count }),
  adoptParallelCandidate: (candidateId: number) =>
    post<Conversation>(`/api/parallel-candidates/${candidateId}/adopt`, {}),
  parallelSettings: () => request<ParallelSettings>('/api/parallel-settings'),
  saveParallelSettings: (values: ParallelSettings) =>
    request<ParallelSettings>('/api/parallel-settings', {
      method: 'PUT',
      body: JSON.stringify(values),
    }),
  saveSimulationSettings: (values: Record<string, unknown>) =>
    request<SimulationSettings>('/api/simulation-settings', {
      method: 'PUT',
      body: JSON.stringify(values),
    }),
}
