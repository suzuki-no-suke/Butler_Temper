import { useState } from 'react'
import { api, type DialogueSettings } from '../api'
import { formatSettings } from '../settingsJson'
import AgentTemplatesUsed from './AgentTemplatesUsed'

// エージェント間対話が使っている両者の設定と、対話用テンプレート・Agent テンプレートを、開いたときに読み込んで表示する
export default function DialogueSettingsView({ dialogueId }: { dialogueId: number }) {
  const [settings, setSettings] = useState<DialogueSettings | null>(null)
  const [error, setError] = useState<string | null>(null)

  const onToggle = (open: boolean) => {
    if (!open || settings) return
    api.dialogueSettings(dialogueId).then(setSettings, (e: Error) => setError(e.message))
  }

  return (
    <details
      className="conversation-settings"
      onToggle={(e) => onToggle((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary>この対話の設定値を見る</summary>
      {error && <p className="error">{error}</p>}
      {!settings && !error && <p className="hint">読み込み中…</p>}
      {settings &&
        (
          [
            ['会話用エージェント', settings.conversation_bot],
            ['Agent', settings.bot],
          ] as const
        ).map(([label, s]) => (
          <div key={label}>
            <h4>
              {label}: {s.bot_name}
            </h4>
            <p className="hint">
              {s.agent_name}（{s.agent_id}）/ バージョン {s.version}
              {s.note && ` — ${s.note}`} / {new Date(s.created_at).toLocaleString('ja-JP')} 保存
            </p>
            <pre className="code">{formatSettings(s.settings)}</pre>
            {label === 'Agent' && <AgentTemplatesUsed settings={s} />}
          </div>
        ))}
      {settings && (
        <>
          <h4>対話用テンプレート</h4>
          {settings.templates.length === 0 && <p className="hint">使っていません</p>}
          {settings.templates.map((t) => (
            <div key={t.name}>
              <p className="hint">
                {t.name}（バージョン {t.version}）
              </p>
              <pre className="code">{t.content}</pre>
            </div>
          ))}
        </>
      )}
    </details>
  )
}
