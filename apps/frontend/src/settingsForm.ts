// BOT 設定（JSON）と、編集画面の入力欄との変換

import type { Settings } from './api'

export interface SettingsDraft {
  systemPrompt: string
  // system_prompt 以外の設定を JSON テキストで持つ
  restJson: string
}

export function toDraft(settings: Settings): SettingsDraft {
  const { system_prompt, ...rest } = settings
  return {
    systemPrompt: typeof system_prompt === 'string' ? system_prompt : '',
    restJson: JSON.stringify(rest, null, 2),
  }
}

export type ParseResult = { ok: true; settings: Settings } | { ok: false; error: string }

export function fromDraft(draft: SettingsDraft): ParseResult {
  let rest: unknown
  try {
    rest = draft.restJson.trim() === '' ? {} : JSON.parse(draft.restJson)
  } catch (e) {
    return { ok: false, error: `JSON の書式が正しくありません: ${(e as Error).message}` }
  }
  if (typeof rest !== 'object' || rest === null || Array.isArray(rest)) {
    return { ok: false, error: 'その他の設定は JSON のオブジェクト（{ ... }）で書いてください' }
  }
  const settings: Settings = { ...(rest as Settings) }
  if ('system_prompt' in settings) {
    return { ok: false, error: 'system_prompt は上の欄に書いてください' }
  }
  if (draft.systemPrompt !== '') settings.system_prompt = draft.systemPrompt
  return { ok: true, settings }
}
