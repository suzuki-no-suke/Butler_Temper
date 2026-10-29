import { describe, expect, it } from 'vitest'
import { formatSettings, parseSettings } from './settingsJson'

describe('settingsJson', () => {
  it('round-trips settings', () => {
    const settings = { system_prompt: 'あなたは執事です', memory: { recent_chars: 5000 } }
    expect(parseSettings(formatSettings(settings))).toEqual({ ok: true, settings })
  })

  it('rejects invalid JSON', () => {
    expect(parseSettings('{').ok).toBe(false)
  })

  it('rejects non-object JSON', () => {
    expect(parseSettings('[1]').ok).toBe(false)
    expect(parseSettings('null').ok).toBe(false)
  })
})
