import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { api, type Bot, type Conversation, type ConversationDetail, type MessageComment } from '../api'
import ConversationComments from '../components/ConversationComments'
import EvaluationSummary from '../components/EvaluationSummary'
import MessageCommentEditor from '../components/MessageCommentEditor'
import MessageParts from '../components/MessageParts'
import RawPanel from '../components/RawPanel'

const ROLE_LABEL = { user: 'あなた', assistant: 'Agent', error: 'エラー' } as const

export default function ChatPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const [bots, setBots] = useState<Bot[]>([])
  const [botId, setBotId] = useState<number | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loaded, setCurrent] = useState<ConversationDetail | null>(null)
  const [input, setInput] = useState('')
  const [rawOpen, setRawOpen] = useState(() => {
    try {
      return localStorage.getItem('bt.rawPanelOpen') === '1'
    } catch {
      return false
    }
  })
  // RAW パラメーター欄に出す発言。null なら最新の RAW のある発言
  const [rawMessageId, setRawMessageId] = useState<number | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.bots().then(setBots, (e: Error) => setError(e.message))
  }, [])

  // URL に会話 ID が無いときは、読み込み済みの会話を表示しない
  const current = conversationId && loaded?.id === Number(conversationId) ? loaded : null

  useEffect(() => {
    try {
      localStorage.setItem('bt.rawPanelOpen', rawOpen ? '1' : '0')
    } catch {
      // 保存できなくても動作には関係しない
    }
  }, [rawOpen])

  const loadConversations = useCallback((id: number) => {
    api.conversations(id).then(setConversations, (e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!conversationId) return
    api.conversation(Number(conversationId)).then(
      (c) => {
        setCurrent(c)
        setBotId(c.bot_id)
        loadConversations(c.bot_id)
      },
      (e: Error) => setError(e.message),
    )
  }, [conversationId, loadConversations])

  const selectBot = (id: number | null) => {
    setBotId(id)
    setConversations([])
    if (id !== null) loadConversations(id)
    navigate('/chat')
  }

  const startConversation = async () => {
    if (botId === null) return
    setError(null)
    try {
      const c = await api.createConversation(botId)
      navigate(`/chat/${c.id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const updateComment = (messageId: number, comment: MessageComment | null) => {
    setCurrent((prev) =>
      prev && {
        ...prev,
        messages: prev.messages.map((m) => (m.id === messageId ? { ...m, comment } : m)),
      },
    )
  }

  const resume = async () => {
    if (!current) return
    setError(null)
    try {
      const c = await api.resumeConversation(current.id)
      navigate(`/chat/${c.id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const startParallel = async (messageId: number) => {
    if (!current) return
    setError(null)
    try {
      const p = await api.startParallelFromConversation(current.id, messageId)
      navigate(`/parallel/${p.id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const send = async (e: FormEvent) => {
    e.preventDefault()
    if (!current || input.trim() === '') return
    setSending(true)
    setError(null)
    try {
      await api.sendMessage(current.id, input)
      setInput('')
      setRawMessageId(null)
      setCurrent(await api.conversation(current.id))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSending(false)
    }
  }

  const selectedBot = bots.find((b) => b.id === botId)
  const withRaw = current?.messages.filter((m) => m.raw_call_id !== null) ?? []
  const rawMessage =
    withRaw.find((m) => m.id === rawMessageId) ?? (withRaw.length ? withRaw[withRaw.length - 1] : null)

  return (
    <div className={`chat-layout${current && rawOpen ? ' with-raw' : ''}`}>
      <aside className="sidebar">
        <label>
          Agent
          <select
            value={botId ?? ''}
            onChange={(e) => selectBot(e.target.value === '' ? null : Number(e.target.value))}
          >
            <option value="">選択してください</option>
            {bots.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}（{b.agent_name}）
                {b.unavailable_reason ? '（停止中）' : ''}
              </option>
            ))}
          </select>
        </label>
        {selectedBot?.unavailable_reason && (
          <p className="error">停止中: {selectedBot.unavailable_reason}</p>
        )}
        <button
          type="button"
          onClick={startConversation}
          disabled={!selectedBot || !!selectedBot.unavailable_reason}
        >
          新しい会話
        </button>
        <ul className="conversation-list">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={c.id === current?.id ? 'link active' : 'link'}
                onClick={() => navigate(`/chat/${c.id}`)}
              >
                #{c.id}（v{c.bot_version}）{c.status === 'stopped' ? ' 停止' : ''}
                <small>{new Date(c.created_at).toLocaleString('ja-JP')}</small>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="chat-main">
        {error && <p className="error">{error}</p>}
        {!current ? (
          <p className="hint">Agent を選んで、新しい会話を始めるか、過去の会話を選んでください。</p>
        ) : (
          <>
            <h2>
              {current.bot_name}（バージョン {current.bot_version}）の会話 #{current.id}
            </h2>
            {current.resumed_from_id && (
              <p className="hint">
                会話 #{current.resumed_from_id} を引き継いだ会話です。
              </p>
            )}
            {current.parallel_conversation_id && (
              <p className="hint">
                <Link to={`/parallel/${current.parallel_conversation_id}`}>
                  並行会話 #{current.parallel_conversation_id}
                </Link>{' '}
                の候補を採用して作った会話です。
              </p>
            )}
            <ol className="messages">
              {current.messages.map((m) => (
                <li
                  key={m.id}
                  className={`message-group${m.id === rawMessage?.id ? ' raw-selected' : ''}`}
                >
                  {m.parts ? (
                    <MessageParts parts={m.parts} />
                  ) : (
                    <div className={`message ${m.role}`}>
                      <div className="message-role">{ROLE_LABEL[m.role]}</div>
                      <div className="message-content">{m.content}</div>
                    </div>
                  )}
                  {m.raw_call_id !== null && m.id !== rawMessage?.id && (
                    <button
                      type="button"
                      className="link raw-select"
                      onClick={() => setRawMessageId(m.id)}
                    >
                      この発言の RAW を見る
                    </button>
                  )}
                  {m.role === 'assistant' && (
                    <button
                      type="button"
                      className="link"
                      onClick={() => startParallel(m.id)}
                    >
                      ここから並行会話
                    </button>
                  )}
                  {m.role === 'assistant' && (
                    <MessageCommentEditor
                      messageId={m.id}
                      comment={m.comment}
                      onSaved={(comment) => updateComment(m.id, comment)}
                    />
                  )}
                </li>
              ))}
            </ol>
            {current.status === 'stopped' ? (
              <div className="stopped">
                <p className="error">この会話はエラーで停止しています。</p>
                <button type="button" onClick={resume}>
                  引き継いで続ける
                </button>
                <p className="hint">
                  エラーより前のやり取りを引き継いだ新しい会話を、同じ Agent のバージョンで始めます。
                </p>
              </div>
            ) : (
              <form className="chat-input" onSubmit={send}>
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="メッセージを入力（Ctrl+Enter で送信）"
                  rows={3}
                  disabled={sending}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                      e.currentTarget.form?.requestSubmit()
                    }
                  }}
                />
                <button type="submit" disabled={sending || input.trim() === ''}>
                  {sending ? '応答待ち…' : '送信'}
                </button>
              </form>
            )}
            <EvaluationSummary
              messages={current.messages}
              onSelect={(id) => {
                setRawMessageId(id)
                setRawOpen(true)
              }}
            />
            <ConversationComments
              conversationId={current.id}
              comments={current.comments}
              onChange={(comments) => setCurrent((prev) => prev && { ...prev, comments })}
            />
          </>
        )}
      </section>

      {current && (
        <aside className="raw-panel">
          <details
            open={rawOpen}
            onToggle={(e) => setRawOpen((e.currentTarget as HTMLDetailsElement).open)}
          >
            <summary>RAW パラメーター</summary>
            <RawPanel
              message={rawMessage}
              label={rawMessage?.role === 'error' ? 'エラー' : 'Agent'}
              commentable={rawMessage?.role === 'assistant'}
            />
          </details>
        </aside>
      )}
    </div>
  )
}
