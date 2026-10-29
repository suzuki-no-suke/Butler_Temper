import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { api, type Bot } from '../api'
import { fromDraft } from '../settingsForm'

const DEFAULT_MODELS = '{\n  "chat": ""\n}'
const DEFAULT_REST = '{\n  "params": {\n    "max_tokens": 1024\n  }\n}'

export default function BotsPage() {
  const navigate = useNavigate()
  const [bots, setBots] = useState<Bot[]>([])
  const [providers, setProviders] = useState<string[]>([])
  const [name, setName] = useState('')
  const [provider, setProvider] = useState('anthropic')
  const [modelsJson, setModelsJson] = useState(DEFAULT_MODELS)
  const [systemPrompt, setSystemPrompt] = useState('')
  const [restJson, setRestJson] = useState(DEFAULT_REST)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.bots().then(setBots, (e: Error) => setError(e.message))
    api.providers().then(setProviders, (e: Error) => setError(e.message))
  }, [])

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    let models: unknown
    try {
      models = JSON.parse(modelsJson)
    } catch {
      setError('モデルの JSON の書式が正しくありません')
      return
    }
    if (typeof models !== 'object' || models === null || Array.isArray(models)) {
      setError('モデルは JSON のオブジェクト（{ ... }）で書いてください')
      return
    }
    const parsed = fromDraft({ systemPrompt, restJson })
    if (!parsed.ok) {
      setError(parsed.error)
      return
    }
    try {
      const bot = await api.createBot({
        name,
        provider,
        models: models as Record<string, unknown>,
        settings: parsed.settings,
        note: '初期設定',
      })
      navigate(`/bots/${bot.id}`)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="page">
      <h2>BOT 一覧</h2>
      <ul className="bot-list">
        {bots.map((b) => (
          <li key={b.id}>
            <Link to={`/bots/${b.id}`}>{b.name}</Link> — {b.provider} / 最新 v{b.latest_version}
            {b.unavailable_reason && <span className="error">（停止中）</span>}
          </li>
        ))}
        {bots.length === 0 && <li className="hint">BOT がまだありません。</li>}
      </ul>

      <h2>BOT を作る</h2>
      <p className="hint">
        プロバイダーとモデルは作成後に変更できません。変える場合は新しい BOT を作ります。
        日付付きのモデル ID がある場合は、日付付きのものを指定してください。
      </p>
      {error && <p className="error">{error}</p>}
      <form className="form" onSubmit={create}>
        <label>
          名前
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          プロバイダー
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label>
          モデル（JSON。会話には "chat" を使う）
          <textarea
            className="code"
            value={modelsJson}
            onChange={(e) => setModelsJson(e.target.value)}
            rows={4}
          />
        </label>
        <label>
          システムプロンプト
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={8}
          />
        </label>
        <label>
          その他の設定（JSON。params は API にそのまま渡す）
          <textarea
            className="code"
            value={restJson}
            onChange={(e) => setRestJson(e.target.value)}
            rows={8}
          />
        </label>
        <button type="submit">作成</button>
      </form>
    </div>
  )
}
