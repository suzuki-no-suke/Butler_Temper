import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import {
  api,
  conversationBotApi,
  dialogueCommentApi,
  type Bot,
  type Dialogue,
  type DialogueDetail,
  type DialogueMessage,
  type MessageComment,
} from '../api'
import ConversationComments from '../components/ConversationComments'
import EvaluationSummary from '../components/EvaluationSummary'
import MessageCommentEditor from '../components/MessageCommentEditor'
import MessageParts from '../components/MessageParts'
import RawPanel from '../components/RawPanel'

// 「自動で進める」で一度に進められるターン数の上限
const MAX_AUTO_TURNS = 50

const SPEAKER_LABEL = { conversation: '会話用エージェント', agent: 'Agent' } as const

const label = (m: DialogueMessage) =>
  m.role === 'error' ? `エラー（${SPEAKER_LABEL[m.speaker]}）` : SPEAKER_LABEL[m.speaker]

export default function DialoguePage() {
  const { dialogueId } = useParams()
  const navigate = useNavigate()
  const [conversationBots, setConversationBots] = useState<Bot[]>([])
  const [bots, setBots] = useState<Bot[]>([])
  const [conversationBotId, setConversationBotId] = useState<number | null>(null)
  const [botId, setBotId] = useState<number | null>(null)
  const [dialogues, setDialogues] = useState<Dialogue[]>([])
  const [loaded, setCurrent] = useState<DialogueDetail | null>(null)
  const [autoTurns, setAutoTurns] = useState(10)
  // 進めている間の表示。自動のときは何ターン目か
  const [progress, setProgress] = useState<string | null>(null)
  const stopRequested = useRef(false)
  const [rawOpen, setRawOpen] = useState(() => {
    try {
      return localStorage.getItem('bt.rawPanelOpen') === '1'
    } catch {
      return false
    }
  })
  const [rawMessageId, setRawMessageId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    conversationBotApi.bots().then(setConversationBots, (e: Error) => setError(e.message))
    api.bots().then(setBots, (e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem('bt.rawPanelOpen', rawOpen ? '1' : '0')
    } catch {
      // 保存できなくても動作には関係しない
    }
  }, [rawOpen])

  const current = dialogueId && loaded?.id === Number(dialogueId) ? loaded : null

  const loadDialogues = useCallback((cid: number | null, bid: number | null) => {
    if (cid === null) {
      setDialogues([])
      return
    }
    api
      .dialogues({ conversationBotId: cid, botId: bid ?? undefined })
      .then(setDialogues, (e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!dialogueId) return
    api.dialogue(Number(dialogueId)).then(
      (d) => {
        setCurrent(d)
        setConversationBotId(d.conversation_bot_id)
        setBotId(d.bot_id)
        loadDialogues(d.conversation_bot_id, d.bot_id)
      },
      (e: Error) => setError(e.message),
    )
  }, [dialogueId, loadDialogues])

  const select = (cid: number | null, bid: number | null) => {
    setConversationBotId(cid)
    setBotId(bid)
    loadDialogues(cid, bid)
    navigate('/dialogue')
  }

  const start = async () => {
    if (conversationBotId === null || botId === null) return
    setError(null)
    try {
      const d = await api.createDialogue(conversationBotId, botId)
      navigate(`/dialogue/${d.id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const startParallel = async (messageId: number) => {
    if (!current) return
    setError(null)
    try {
      const p = await api.startParallelFromDialogue(current.id, messageId)
      navigate(`/parallel/${p.id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const resume = async () => {
    if (!current) return
    setError(null)
    try {
      const d = await api.resumeDialogue(current.id)
      navigate(`/dialogue/${d.id}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  // turns ターン進める。エラーが起きるか、止めるよう言われたらそこで終わる
  const advance = async (turns: number) => {
    if (!current) return
    const id = current.id
    stopRequested.current = false
    setError(null)
    setRawMessageId(null)
    try {
      for (let i = 1; i <= turns; i++) {
        setProgress(turns === 1 ? '発言待ち…' : `自動で進めています（${i} / ${turns} ターン目）`)
        const saved = await api.advanceDialogue(id)
        setCurrent(await api.dialogue(id))
        if (saved.some((m) => m.role === 'error') || stopRequested.current) break
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setProgress(null)
      loadDialogues(conversationBotId, botId)
    }
  }

  const updateComment = (messageId: number, comment: MessageComment | null) => {
    setCurrent(
      (prev) =>
        prev && {
          ...prev,
          messages: prev.messages.map((m) => (m.id === messageId ? { ...m, comment } : m)),
        },
    )
  }

  const conversationBot = conversationBots.find((b) => b.id === conversationBotId)
  const bot = bots.find((b) => b.id === botId)
  const stopped = [conversationBot, bot].find((b) => b?.unavailable_reason)
  const withRaw = current?.messages.filter((m) => m.raw_call_id !== null) ?? []
  const rawMessage =
    withRaw.find((m) => m.id === rawMessageId) ?? (withRaw.length ? withRaw[withRaw.length - 1] : null)
  const running = progress !== null

  return (
    <div className={`chat-layout${current && rawOpen ? ' with-raw' : ''}`}>
      <aside className="sidebar">
        <label>
          会話用エージェント
          <select
            value={conversationBotId ?? ''}
            onChange={(e) => select(e.target.value === '' ? null : Number(e.target.value), botId)}
          >
            <option value="">選択してください</option>
            {conversationBots.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}（{b.agent_name}）{b.unavailable_reason ? '（停止中）' : ''}
              </option>
            ))}
          </select>
        </label>
        <label>
          話し相手の Agent
          <select
            value={botId ?? ''}
            onChange={(e) =>
              select(conversationBotId, e.target.value === '' ? null : Number(e.target.value))
            }
          >
            <option value="">選択してください</option>
            {bots.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}（{b.agent_name}）{b.unavailable_reason ? '（停止中）' : ''}
              </option>
            ))}
          </select>
        </label>
        {stopped && <p className="error">停止中: {stopped.unavailable_reason}</p>}
        <button type="button" onClick={start} disabled={!conversationBot || !bot || !!stopped}>
          新しい対話
        </button>
        <ul className="conversation-list">
          {dialogues.map((d) => (
            <li key={d.id}>
              <button
                type="button"
                className={d.id === current?.id ? 'link active' : 'link'}
                onClick={() => navigate(`/dialogue/${d.id}`)}
              >
                #{d.id} {d.bot_name}（v{d.conversation_bot_version} × v{d.bot_version}）
                {d.status === 'stopped' ? ' 停止' : ''}
                <small>{new Date(d.created_at).toLocaleString('ja-JP')}</small>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="chat-main">
        {error && <p className="error">{error}</p>}
        {!current ? (
          <p className="hint">
            会話用エージェントを選んで、新しい対話を始めるか、過去の対話を選んでください。
          </p>
        ) : (
          <>
            <h2>
              {current.conversation_bot_name}（v{current.conversation_bot_version}）と{' '}
              {current.bot_name}（v{current.bot_version}）の対話 #{current.id}
            </h2>
            <p className="hint">
              テンプレート:{' '}
              {current.templates.length === 0
                ? 'なし'
                : current.templates.map((t) => `${t.name}（v${t.version}）`).join('、')}
              {current.resumed_from_id && ` / 対話 #${current.resumed_from_id} を引き継いだ対話です。`}
            </p>
            <ol className="messages">
              {current.messages.map((m) => (
                <li
                  key={m.id}
                  className={`message-group${m.id === rawMessage?.id ? ' raw-selected' : ''}`}
                >
                  {m.parts && m.role === 'speech' ? (
                    <MessageParts parts={m.parts} />
                  ) : (
                    <div
                      className={`message ${
                        m.role === 'error' ? 'error' : m.speaker === 'conversation' ? 'user' : 'assistant'
                      }`}
                    >
                      <div className="message-role">{label(m)}</div>
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
                  {m.role === 'speech' && m.speaker === 'agent' && (
                    <button
                      type="button"
                      className="link"
                      onClick={() => startParallel(m.id)}
                    >
                      ここから並行会話
                    </button>
                  )}
                  {m.role === 'speech' && (
                    <MessageCommentEditor
                      messageId={m.id}
                      comment={m.comment}
                      commentApi={dialogueCommentApi}
                      label="この発言を評価する"
                      onSaved={(comment) => updateComment(m.id, comment)}
                    />
                  )}
                </li>
              ))}
            </ol>
            {current.status === 'stopped' ? (
              <div className="stopped">
                <p className="error">この対話はエラーで停止しています。</p>
                <button type="button" onClick={resume}>
                  引き継いで続ける
                </button>
                <p className="hint">
                  エラーより前のやり取りを引き継いだ新しい対話を、同じバージョン（テンプレートを含む）で始めます。
                </p>
              </div>
            ) : (
              <div className="dialogue-controls">
                <button type="button" onClick={() => advance(1)} disabled={running}>
                  次の発言を行う（1 ターン）
                </button>
                <label>
                  <input
                    type="number"
                    min={1}
                    max={MAX_AUTO_TURNS}
                    value={autoTurns}
                    disabled={running}
                    onChange={(e) =>
                      setAutoTurns(Math.min(MAX_AUTO_TURNS, Math.max(1, Number(e.target.value) || 1)))
                    }
                  />
                  ターン
                </label>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => advance(autoTurns)}
                  disabled={running}
                >
                  自動で進める（最大 {MAX_AUTO_TURNS} ターン）
                </button>
                {running && (
                  <>
                    <span className="hint">{progress}</span>
                    <button
                      type="button"
                      className="link"
                      onClick={() => {
                        stopRequested.current = true
                      }}
                    >
                      このターンで止める
                    </button>
                  </>
                )}
              </div>
            )}
            <p className="hint">
              1 ターンは、会話用エージェントの発言と、それへの Agent の応答の一組です。
            </p>
            <EvaluationSummary
              messages={current.messages}
              title="発言への評価とコメント（ここまで）"
              speakerLabel={label}
              onSelect={(id) => {
                setRawMessageId(id)
                setRawOpen(true)
              }}
            />
            <ConversationComments
              conversationId={current.id}
              comments={current.comments}
              commentApi={dialogueCommentApi}
              title="対話全体へのコメント"
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
              label={rawMessage ? label(rawMessage) : ''}
              commentable={rawMessage?.role === 'speech'}
            />
          </details>
        </aside>
      )}
    </div>
  )
}
