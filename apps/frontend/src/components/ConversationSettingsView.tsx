import { useState } from 'react'
import { api, type ConversationSettings } from '../api'
import { formatSettings } from '../settingsJson'

// 会話が使っている BOT 設定を、開いたときに読み込んで表示する
export default function ConversationSettingsView({ conversationId }: { conversationId: number }) {
  const [settings, setSettings] = useState<ConversationSettings | null>(null)
  const [error, setError] = useState<string | null>(null)

  const onToggle = (open: boolean) => {
    if (!open || settings) return
    api.conversationSettings(conversationId).then(setSettings, (e: Error) => setError(e.message))
  }

  return (
    <details
      className="conversation-settings"
      onToggle={(e) => onToggle((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary>この会話の設定値を見る</summary>
      {error && <p className="error">{error}</p>}
      {!settings && !error && <p className="hint">読み込み中…</p>}
      {settings && (
        <>
          <p className="hint">
            {settings.agent_name}（{settings.agent_id}）/ バージョン {settings.version}
            {settings.note && ` — ${settings.note}`} /{' '}
            {new Date(settings.created_at).toLocaleString('ja-JP')} 保存
          </p>
          <pre className="code">{formatSettings(settings.settings)}</pre>
        </>
      )}
    </details>
  )
}
