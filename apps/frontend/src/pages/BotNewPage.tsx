import { useState, type FormEvent } from 'react'
import { useNavigate, useOutletContext } from 'react-router'
import { api } from '../api'
import AgentInfo from '../components/AgentInfo'
import { formatSettings, parseSettings } from '../settingsJson'
import type { BotsContext } from './BotsLayout'

export default function BotNewPage() {
  const { agents, reloadBots } = useOutletContext<BotsContext>()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [agentId, setAgentId] = useState('')
  const [settingsText, setSettingsText] = useState('')
  const [error, setError] = useState<string | null>(null)

  const agent = agents.find((a) => a.id === agentId)

  const selectAgent = (id: string) => {
    setAgentId(id)
    const selected = agents.find((a) => a.id === id)
    setSettingsText(selected ? formatSettings(selected.default_settings) : '')
    if (selected && name === '') setName(selected.name)
  }

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!agent) return
    const parsed = parseSettings(settingsText)
    if (!parsed.ok) {
      setError(parsed.error)
      return
    }
    try {
      const bot = await api.createBot({
        name,
        agent_id: agent.id,
        settings: parsed.settings,
        note: '作成時の設定',
      })
      reloadBots()
      navigate(`/bots/${bot.id}`)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="page">
      <h2>新しい Agent を作る</h2>
      <form className="form" onSubmit={create}>
        <label>
          採用する AgentCore
          <select value={agentId} onChange={(e) => selectAgent(e.target.value)} required>
            <option value="">選択してください</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        {agent && <AgentInfo agent={agent} />}
        <label>
          名前
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        {agent && (
          <label>
            Agent 設定（JSON。初期値は AgentCore の既定の Agent 設定）
            <textarea
              className="code"
              value={settingsText}
              onChange={(e) => setSettingsText(e.target.value)}
              rows={24}
            />
          </label>
        )}
        {error && <pre className="error">{error}</pre>}
        <button type="submit" disabled={!agent}>
          作成
        </button>
      </form>
    </div>
  )
}
