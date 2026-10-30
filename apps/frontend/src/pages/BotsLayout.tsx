import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router'
import { type Agent, type Bot } from '../api'
import type { BotKind } from '../botKinds'

export interface BotsContext {
  agents: Agent[]
  reloadBots: () => void
  kind: BotKind
}

export default function BotsLayout({ kind }: { kind: BotKind }) {
  const [bots, setBots] = useState<Bot[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [error, setError] = useState<string | null>(null)

  const reloadBots = useCallback(() => {
    kind.botApi.bots().then(setBots, (e: Error) => setError(e.message))
  }, [kind])

  useEffect(() => {
    reloadBots()
    kind.botApi.agents().then(setAgents, (e: Error) => setError(e.message))
  }, [kind, reloadBots])

  const context: BotsContext = { agents, reloadBots, kind }

  return (
    <div className="bots-layout">
      <aside className="sidebar">
        <NavLink to={`${kind.basePath}/new`} className="button">
          新しい{kind.label}を作る
        </NavLink>
        <h3>設定済みの{kind.label}</h3>
        {error && <p className="error">{error}</p>}
        <ul className="bot-list">
          {bots.map((b) => (
            <li key={b.id}>
              <NavLink to={`${kind.basePath}/${b.id}`}>
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
