import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { api, conversationBotApi, type Bot, type Dialogue } from '../api'
import DialogueSettingsView from '../components/DialogueSettingsView'

const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString('ja-JP') : '—')

export default function DialogueHistoryPage() {
  const navigate = useNavigate()
  const [conversationBots, setConversationBots] = useState<Bot[]>([])
  const [bots, setBots] = useState<Bot[]>([])
  const [conversationBotId, setConversationBotId] = useState<number | null>(null)
  const [botId, setBotId] = useState<number | null>(null)
  const [dialogues, setDialogues] = useState<Dialogue[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    conversationBotApi.bots().then(setConversationBots, (e: Error) => setError(e.message))
    api.bots().then(setBots, (e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    api
      .dialogues({ conversationBotId: conversationBotId ?? undefined, botId: botId ?? undefined })
      .then(setDialogues, (e: Error) => setError(e.message))
  }, [conversationBotId, botId])

  const resume = async (d: Dialogue) => {
    setError(null)
    try {
      const resumed = await api.resumeDialogue(d.id)
      navigate(`/dialogue/${resumed.id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const toId = (value: string) => (value === '' ? null : Number(value))

  return (
    <div className="page">
      <h2>エージェント間対話の履歴</h2>
      <label className="filter">
        会話用エージェントで絞り込む
        <select
          value={conversationBotId ?? ''}
          onChange={(e) => setConversationBotId(toId(e.target.value))}
        >
          <option value="">すべて</option>
          {conversationBots.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      <label className="filter">
        Agent で絞り込む
        <select value={botId ?? ''} onChange={(e) => setBotId(toId(e.target.value))}>
          <option value="">すべて</option>
          {bots.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      {error && <p className="error">{error}</p>}
      <ul className="history-list">
        {dialogues.map((d) => (
          <li key={d.id} className="history-item">
            <div className="history-head">
              <strong>#{d.id}</strong>
              <span>
                {d.conversation_bot_name}（v{d.conversation_bot_version}）× {d.bot_name}（v
                {d.bot_version}）
              </span>
              {d.status === 'stopped' && <span className="badge error">エラーで停止</span>}
              {d.resumed_from_id && <span className="badge">#{d.resumed_from_id} から引き継ぎ</span>}
            </div>
            <div className="history-preview">{d.preview || '（発言なし）'}</div>
            <div className="history-meta">
              {d.message_count} 件 / テンプレート{' '}
              {d.templates.length === 0
                ? 'なし'
                : d.templates.map((t) => `${t.name}（v${t.version}）`).join('、')}{' '}
              / 開始 {formatDate(d.created_at)} / 最終 {formatDate(d.last_message_at)}
            </div>
            <DialogueSettingsView dialogueId={d.id} />
            <div className="button-row">
              <button type="button" onClick={() => navigate(`/dialogue/${d.id}`)}>
                {d.status === 'active' ? '開いて続ける' : '開く'}
              </button>
              {d.status === 'stopped' && (
                <button type="button" className="secondary" onClick={() => resume(d)}>
                  引き継いで続ける
                </button>
              )}
            </div>
          </li>
        ))}
        {dialogues.length === 0 && <li className="hint">対話はまだありません。</li>}
      </ul>
    </div>
  )
}
