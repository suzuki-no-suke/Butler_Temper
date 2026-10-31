import type { ConversationSettings } from '../api'
import { formatSettings } from '../settingsJson'

// 開始時に固定した Agent テンプレートと、それを埋め込んだ設定（実際に使う設定）
export default function AgentTemplatesUsed({ settings }: { settings: ConversationSettings }) {
  if (settings.resolved_settings === null) {
    return <p className="hint">Agent テンプレートの仕組みより前の記録です（上の設定をそのまま使います）。</p>
  }
  return (
    <>
      <h4>Agent テンプレート（開始時に固定）</h4>
      {settings.agent_templates.length === 0 && <p className="hint">使っていません</p>}
      {settings.agent_templates.map((t) => (
        <div key={t.name}>
          <p className="hint">
            {t.name}（バージョン {t.version}）
          </p>
          <pre className="code">{t.content}</pre>
        </div>
      ))}
      {settings.agent_templates.length > 0 && (
        <details>
          <summary>Agent テンプレートを埋め込んだ設定（実際に使う設定）</summary>
          <pre className="code">{formatSettings(settings.resolved_settings)}</pre>
        </details>
      )}
    </>
  )
}
