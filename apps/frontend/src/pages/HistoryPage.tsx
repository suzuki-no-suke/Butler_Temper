import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { api, type Bot, type Conversation } from '../api'

const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString('ja-JP') : '—')

export default function HistoryPage() {
  const navigate = useNavigate()
  const [bots, setBots] = useState<Bot[]>([])
  const [botId, setBotId] = useState<number | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.bots().then(setBots, (e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    api.conversations(botId ?? undefined).then(setConversations, (e: Error) => setError(e.message))
  }, [botId])

  const resume = async (c: Conversation) => {
    setError(null)
    try {
      const resumed = await api.resumeConversation(c.id)
      navigate(`/chat/${resumed.id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="page">
      <h2>チャット履歴</h2>
      <label className="filter">
        BOT で絞り込む
        <select
          value={botId ?? ''}
          onChange={(e) => setBotId(e.target.value === '' ? null : Number(e.target.value))}
        >
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
        {conversations.map((c) => (
          <li key={c.id} className="history-item">
            <div className="history-head">
              <strong>#{c.id}</strong>
              <span>
                {c.bot_name}（v{c.bot_version}）
              </span>
              {c.status === 'stopped' && <span className="badge error">エラーで停止</span>}
              {c.resumed_from_id && <span className="badge">#{c.resumed_from_id} から引き継ぎ</span>}
            </div>
            <div className="history-preview">{c.preview || '（発言なし）'}</div>
            <div className="history-meta">
              {c.message_count} 件 / 開始 {formatDate(c.created_at)} / 最終{' '}
              {formatDate(c.last_message_at)}
            </div>
            <div className="button-row">
              <button type="button" onClick={() => navigate(`/chat/${c.id}`)}>
                {c.status === 'active' ? '開いて続ける' : '開く'}
              </button>
              {c.status === 'stopped' && (
                <button type="button" className="secondary" onClick={() => resume(c)}>
                  引き継いで続ける
                </button>
              )}
            </div>
          </li>
        ))}
        {conversations.length === 0 && <li className="hint">会話はまだありません。</li>}
      </ul>
    </div>
  )
}
