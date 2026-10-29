import { describe, expect, it } from 'vitest'
import { fromDraft, toDraft } from './settingsForm'

describe('settingsForm', () => {
  it('round-trips settings', () => {
    const settings = { system_prompt: 'あなたは執事です', params: { max_tokens: 512 } }
    expect(fromDraft(toDraft(settings))).toEqual({ ok: true, settings })
  })

  it('omits empty system prompt', () => {
    expect(fromDraft({ systemPrompt: '', restJson: '{}' })).toEqual({ ok: true, settings: {} })
  })

  it('rejects invalid JSON', () => {
    expect(fromDraft({ systemPrompt: '', restJson: '{' }).ok).toBe(false)
  })

  it('rejects non-object JSON', () => {
    expect(fromDraft({ systemPrompt: '', restJson: '[1]' }).ok).toBe(false)
  })

  it('rejects system_prompt inside JSON', () => {
    expect(fromDraft({ systemPrompt: '', restJson: '{"system_prompt": "x"}' }).ok).toBe(false)
  })
})
