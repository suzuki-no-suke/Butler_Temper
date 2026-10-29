import type { Agent } from '../api'

export default function AgentInfo({ agent }: { agent: Agent }) {
  return (
    <div className="agent-info">
      <div className="agent-name">{agent.name}</div>
      <dl>
        <dt>Agent ID</dt>
        <dd>
          <code>{agent.id}</code>
        </dd>
        <dt>モデル</dt>
        <dd>
          {Object.entries(agent.models).map(([role, model]) => (
            <div key={role}>
              {role}: <code>{model}</code>
            </div>
          ))}
        </dd>
      </dl>
      <p>{agent.description}</p>
    </div>
  )
}
