import { useEffect, useState, type FormEvent } from 'react'
import { api, type Settings, type SettingsChatMessage } from '../api'

interface Props {
  botId: number
  // 画面上の編集中の設定（JSON テキスト）
  currentSettings: string
  // 変更案が来たら、編集中の設定に反映する
  onProposal: (settings: Settings) => void
}

const ROLE_LABEL = { user: 'あなた', assistant: 'アシスタント', error: 'エラー' } as const

export default function SettingsChat({ botId, currentSettings, onProposal }: Props) {
  const [messages, setMessages] = useState<SettingsChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.settingsChat(botId).then(setMessages, (e: Error) => setError(e.message))
  }, [botId])

  const send = async (e: FormEvent) => {
    e.preventDefault()
    if (input.trim() === '') return
    setSending(true)
    setError(null)
    try {
      const result = await api.sendSettingsChat(botId, input, currentSettings)
      setMessages((prev) => [...prev, ...result.messages])
      setInput('')
      if (result.proposed_settings) onProposal(result.proposed_settings)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSending(false)
    }
  }

  const clear = async () => {
    setError(null)
    try {
      await api.clearSettingsChat(botId)
      setMessages([])
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <section className="settings-chat">
      <h3>設定変更チャット</h3>
      <p className="hint">
        要望を書くと、変更案が「編集中の設定」に反映されます。保存するまで BOT は変わりません。
      </p>
      <ol className="messages">
        {messages.map((m) => (
          <li key={m.id} className={`message ${m.role === 'assistant' ? 'assistant' : m.role}`}>
            <div className="message-role">
              {ROLE_LABEL[m.role]}
              {m.proposed_settings && '（変更案あり）'}
            </div>
            <div className="message-content">{m.content}</div>
          </li>
        ))}
      </ol>
      {error && <p className="error">{error}</p>}
      <form className="chat-input" onSubmit={send}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="例: もう少しくだけた口調にして（Ctrl+Enter で送信）"
          aria-label="設定変更の要望"
          rows={3}
          disabled={sending}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) e.currentTarget.form?.requestSubmit()
          }}
        />
        <button type="submit" disabled={sending || input.trim() === ''}>
          {sending ? '考え中…' : '送信'}
        </button>
      </form>
      {messages.length > 0 && (
        <button type="button" className="link" onClick={clear}>
          やり取りを消す
        </button>
      )}
    </section>
  )
}
