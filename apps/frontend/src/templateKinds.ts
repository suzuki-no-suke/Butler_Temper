import { api, type Template, type TemplateDetail, type TemplateVersion } from './api'

// 対話用テンプレートと Agent テンプレートは、同じ画面で別々に管理する（混ぜない）
export interface TemplateKind {
  // 画面の URL の起点
  basePath: string
  // 画面に出す呼び名
  label: string
  // 設定の中での書き方
  placeholder: (name: string) => string
  // どこに埋め込めて、いつの本文が入るか
  usage: string
  list: () => Promise<Template[]>
  get: (id: number) => Promise<TemplateDetail>
  create: (body: { name: string; content: string; note: string }) => Promise<TemplateDetail>
  createVersion: (id: number, body: { content: string; note: string }) => Promise<TemplateVersion>
}

export const DIALOGUE_TEMPLATE_KIND: TemplateKind = {
  basePath: '/templates',
  label: '対話用テンプレート',
  placeholder: (name) => `{{template:${name}}}`,
  usage:
    '会話用エージェントの設定の中に書くと、エージェント間対話を始めたときの最新バージョンの本文が埋め込まれます。',
  list: api.templates,
  get: api.template,
  create: api.createTemplate,
  createVersion: api.createTemplateVersion,
}

export const AGENT_TEMPLATE_KIND: TemplateKind = {
  basePath: '/agent-templates',
  label: 'Agent テンプレート',
  placeholder: (name) => `{{agent_template:${name}}}`,
  usage:
    'Agent 設定の中の文字列に書くと、会話・エージェント間対話・並行会話を始めたときの最新バージョンの本文が埋め込まれ、その会話の中で固定されます。テンプレートが無ければ始められません。',
  list: api.agentTemplates,
  get: api.agentTemplate,
  create: api.createAgentTemplate,
  createVersion: api.createAgentTemplateVersion,
}
