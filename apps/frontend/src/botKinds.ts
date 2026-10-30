import { agentBotApi, conversationBotApi, type BotApi } from './api'

// Agent と会話用エージェントは、同じ画面で別々に管理する
export interface BotKind {
  botApi: BotApi
  // 画面の URL の起点
  basePath: string
  // 画面に出す呼び名
  label: string
}

export const AGENT_KIND: BotKind = { botApi: agentBotApi, basePath: '/bots', label: 'Agent' }
export const CONVERSATION_KIND: BotKind = {
  botApi: conversationBotApi,
  basePath: '/conversation-bots',
  label: '会話用エージェント',
}
