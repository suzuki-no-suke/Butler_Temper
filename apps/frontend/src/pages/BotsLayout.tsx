import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router'
import { api, type Agent, type Bot } from '../api'

export interface BotsContext {
  agents: Agent[]
  reloadBots: () => void
}

export default function BotsLayout() {
  const [bots, setBots] = useState<Bot[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [error, setError] = useState<string | null>(null)

  const reloadBots = useCallback(() => {
    api.bots().then(setBots, (e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    reloadBots()
    api.agents().then(setAgents, (e: Error) => setError(e.message))
  }, [reloadBots])

  const context: BotsContext = { agents, reloadBots }

  return (
    <div className="bots-layout">
      <aside className="sidebar">
        <NavLink to="/bots/new" className="button">
          新しい Agent を作る
        </NavLink>
        <h3>設定済みの Agent</h3>
        {error && <p className="error">{error}</p>}
        <ul className="bot-list">
          {bots.map((b) => (
            <li key={b.id}>
              <NavLink to={`/bots/${b.id}`}>
                {b.name}
                {b.unavailable_reason && <span className="error">（停止中）</span>}
                <small>
                  {b.agent_name} / v{b.latest_version}
                </small>
              </NavLink>
            </li>
          ))}
          {bots.length === 0 && <li className="hint">まだありません</li>}
        </ul>
      </aside>
      <section>
        <Outlet context={context} />
      </section>
    </div>
  )
}
