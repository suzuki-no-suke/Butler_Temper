import { useEffect, useState } from 'react'
import { api, type SimulationSettings } from '../api'

const json = (value: unknown) => JSON.stringify(value, null, 2)

// グローバル設定。バージョン管理はしない（実行のたびに、使った値が実行記録に残る）
export default function SimulationSettingsEditor({ onSaved }: { onSaved?: () => void } = {}) {
  const [settings, setSettings] = useState<SimulationSettings | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    api.simulationSettings().then((s) => {
      setSettings(s)
      setText(json(s.values))
    }, (e: Error) => setError(e.message))
  }, [])

  const save = async () => {
    setError(null)
    setMessage(null)
    let values: Record<string, unknown>
    try {
      values = JSON.parse(text) as Record<string, unknown>
    } catch {
      setError('JSON として読めません')
      return
    }
    try {
      const saved = await api.saveSimulationSettings(values)
      setSettings(saved)
      setText(json(saved.values))
      setMessage('保存しました')
      onSaved?.()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <details className="agent-info">
      <summary>グローバル設定（GlobalSimulatingParameter）</summary>
      {settings && (
        <ul>
          {Object.entries(settings.descriptions).map(([key, description]) => (
            <li key={key}>
              <span className="code">{key}</span>: {description}（既定 {json(settings.defaults[key])}）
            </li>
          ))}
        </ul>
      )}
      <div className="form">
        <textarea
          className="code"
          rows={Math.max(6, text.split('\n').length + 1)}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="button-row">
          <button type="button" onClick={save}>
            保存する
          </button>
        </div>
        {message && <p className="notice">{message}</p>}
        {error && <p className="error">{error}</p>}
      </div>
    </details>
  )
}
