// Agent の設定 JSON と、編集欄のテキストとの変換

import type { Settings } from './api'

export function formatSettings(settings: Settings): string {
  return JSON.stringify(settings, null, 2)
}

export type ParseResult = { ok: true; settings: Settings } | { ok: false; error: string }

export function parseSettings(text: string): ParseResult {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch (e) {
    return { ok: false, error: `JSON の書式が正しくありません: ${(e as Error).message}` }
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return { ok: false, error: '設定は JSON のオブジェクト（{ ... }）で書いてください' }
  }
  return { ok: true, settings: value as Settings }
}
