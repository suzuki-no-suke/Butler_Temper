import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import {
  api,
  type Bot,
  type ParallelCandidate,
  type ParallelConversation,
  type ParallelConversationDetail,
} from '../api'
import MessageParts from '../components/MessageParts'
import RawPanel, { type RawTarget } from '../components/RawPanel'

const ROLE_LABEL = { user: 'あなた', assistant: 'Agent', error: 'エラー' } as const
const SOURCE_HINT = {
  conversation: 'チャットの会話の、ここまでの発言を写しています。',
  dialogue: 'エージェント間対話の、ここまでの発言を写しています。',
  new: '会話の最初から始めた並行会話です。',
} as const
const STATUS_LABEL: Record<ParallelCandidate['status'], string> = {
  pending: '待ち',
  running: '生成中',
  succeeded: '完了',
  failed: '失敗',
}
// 候補を作っている間、読み直す間隔
const POLL_MS = 2000
const DEFAULT_COUNT = 10

const formatDate = (iso: string) => new Date(iso).toLocaleString('ja-JP')

// 並行会話。分かれる位置までの会話を写して持ち、同じ入力への応答（候補）を何パターンも作る。
// 一つを採用すると、新しい会話として続ける。元の会話へは戻らない
export default function ParallelPage() {
  const { parallelId } = useParams()
  const navigate = useNavigate()
  const [list, setList] = useState<ParallelConversation[]>([])
  const [bots, setBots] = useState<Bot[]>([])
  const [botId, setBotId] = useState<number | null>(null)
  const [loaded, setLoaded] = useState<ParallelConversationDetail | null>(null)
  const [input, setInput] = useState('')
  const [count, setCount] = useState(DEFAULT_COUNT)
  const [sending, setSending] = useState(false)
  // RAW パラメーター欄に出すもの。m: 写した発言、c: 候補
  const [rawKey, setRawKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const current = parallelId && loaded?.id === Number(parallelId) ? loaded : null

  const loadList = useCallback(() => {
    api.parallelConversations().then(setList, (e: Error) => setError(e.message))
  }, [])

  useEffect(loadList, [loadList])

  useEffect(() => {
    api.bots().then(setBots, (e: Error) => setError(e.message))
  }, [])

  const reload = useCallback(() => {
    if (!parallelId) return
    api.parallelConversation(Number(parallelId)).then(setLoaded, (e: Error) => setError(e.message))
  }, [parallelId])

  useEffect(reload, [reload])

  // 作っている候補があれば、終わるまで読み直す
  const working = current?.rounds.some((r) =>
    r.candidates.some((c) => c.status === 'pending' || c.status === 'running'),
  )
  useEffect(() => {
    if (!working) return
    const timer = setTimeout(reload, POLL_MS)
    return () => clearTimeout(timer)
  }, [working, current, reload])

  const run = async (e: FormEvent) => {
    e.preventDefault()
    if (!current || input.trim() === '') return
    setSending(true)
    setError(null)
    try {
      await api.createParallelRound(current.id, input, count)
      reload()
      loadList()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSending(false)
    }
  }

  const startNew = async () => {
    if (botId === null) return
    setError(null)
    try {
      const p = await api.startParallelNew(botId)
      loadList()
      navigate(`/parallel/${p.id}`)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const adopt = async (candidateId: number) => {
    setError(null)
    try {
      const c = await api.adoptParallelCandidate(candidateId)
      navigate(`/chat/${c.id}`)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const rawTargets: Record<string, { target: RawTarget; label: string }> = {}
  if (current) {
    for (const m of current.messages) {
      rawTargets[`m:${m.id}`] = { target: { ...m, comment: null }, label: ROLE_LABEL[m.role] }
    }
    for (const r of current.rounds) {
      for (const c of r.candidates) {
        rawTargets[`c:${c.id}`] = {
          target: {
            seq: current.messages.length + 1,
            raw_call_id: c.raw_call_id,
            agent_state: c.agent_state,
            parts: c.parts,
            comment: null,
          },
          label: `候補 ${c.index + 1}「${r.content}」`,
        }
      }
    }
  }
  const raw = rawKey ? rawTargets[rawKey] : undefined

  const rawButton = (key: string, rawCallId: number | null) =>
    rawCallId !== null &&
    key !== rawKey && (
      <button type="button" className="link raw-select" onClick={() => setRawKey(key)}>
        RAW を見る
      </button>
    )

  return (
    <div className={`chat-layout${current ? ' with-raw' : ''}`}>
      <aside className="sidebar">
        <label>
          Agent
          <select
            value={botId ?? ''}
            onChange={(e) => setBotId(e.target.value === '' ? null : Number(e.target.value))}
          >
            <option value="">選択してください</option>
            {bots.map((b) => (
              <option key={b.id} value={b.id} disabled={!!b.unavailable_reason}>
                {b.name}（{b.agent_name}）
                {b.unavailable_reason ? '（停止中）' : ''}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={startNew} disabled={botId === null}>
          新しい会話を並行会話
        </button>
        <h3>並行会話</h3>
        <ul className="conversation-list">
          {list.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className={p.id === current?.id ? 'link active' : 'link'}
                onClick={() => navigate(`/parallel/${p.id}`)}
              >
                #{p.id} {p.bot_name}（v{p.bot_version}）・{p.round_count} 回
                <small>{p.preview}</small>
                <small>{formatDate(p.created_at)}</small>
              </button>
            </li>
          ))}
        </ul>
        {list.length === 0 && (
          <p className="hint">
            上で Agent を選んで最初から始めるか、チャットやエージェント間対話の Agent
            の発言から「ここから並行会話」で始めます。
          </p>
        )}
      </aside>

      <section className="chat-main">
        {error && <p className="error">{error}</p>}
        {!current ? (
          <p className="hint">左の一覧から並行会話を選んでください。</p>
        ) : (
          <>
            <h2>
              {current.bot_name}（バージョン {current.bot_version}）の並行会話 #{current.id}
            </h2>
            <p className="hint">{SOURCE_HINT[current.source_kind]}</p>
            <ol className="messages">
              {current.messages.map((m) => (
                <li
                  key={m.id}
                  className={`message-group${rawKey === `m:${m.id}` ? ' raw-selected' : ''}`}
                >
                  {m.parts ? (
                    <MessageParts parts={m.parts} />
                  ) : (
                    <div className={`message ${m.role}`}>
                      <div className="message-role">{ROLE_LABEL[m.role]}</div>
                      <div className="message-content">{m.content}</div>
                    </div>
                  )}
                  {rawButton(`m:${m.id}`, m.raw_call_id)}
                </li>
              ))}
            </ol>

            {current.rounds.map((r, i) => (
              <section key={r.id} className="parallel-round">
                <h3>
                  {i + 1} 回目（{r.count} パターン・{formatDate(r.created_at)}）
                </h3>
                <div className="message user">
                  <div className="message-role">あなた</div>
                  <div className="message-content">{r.content}</div>
                </div>
                <ol className="parallel-candidates">
                  {r.candidates.map((c) => (
                    <li
                      key={c.id}
                      className={`parallel-candidate message-group${
                        rawKey === `c:${c.id}` ? ' raw-selected' : ''
                      }`}
                    >
                      <div className="parallel-candidate-head">
                        <strong>候補 {c.index + 1}</strong>
                        <span className={`status-${c.status}`}>{STATUS_LABEL[c.status]}</span>
                      </div>
                      {c.status === 'succeeded' &&
                        (c.parts ? (
                          <MessageParts parts={c.parts} />
                        ) : (
                          <div className="message assistant">
                            <div className="message-role">Agent</div>
                            <div className="message-content">{c.text}</div>
                          </div>
                        ))}
                      {c.status === 'failed' && <pre className="error">{c.error}</pre>}
                      <div className="parallel-candidate-actions">
                        {rawButton(`c:${c.id}`, c.raw_call_id)}
                        {c.status === 'succeeded' && (
                          <button type="button" onClick={() => adopt(c.id)}>
                            採用して会話を続ける
                          </button>
                        )}
                        {c.conversation_ids.length > 0 && (
                          <span className="hint">
                            採用した会話:{' '}
                            {c.conversation_ids.map((id) => (
                              <Link key={id} to={`/chat/${id}`}>
                                #{id}{' '}
                              </Link>
                            ))}
                          </span>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
            ))}

            <form className="chat-input" onSubmit={run}>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="あなたの入力（Ctrl+Enter で実行）。言い回しを変えて何回でも試せます"
                rows={3}
                disabled={sending}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.currentTarget.form?.requestSubmit()
                  }
                }}
              />
              <label>
                パターン数
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                />
              </label>
              <button type="submit" disabled={sending || input.trim() === '' || count < 1}>
                {sending ? '送信中…' : `${count} パターン作る`}
              </button>
            </form>
            <p className="hint">
              候補は裏で作り、できたものから表示します。同時に作る数は
              <Link to="/parallel-settings">並行会話設定</Link>で変えられます。
            </p>
          </>
        )}
      </section>

      {current && (
        <aside className="raw-panel">
          <details open>
            <summary>RAW パラメーター</summary>
            {raw ? (
              <RawPanel message={raw.target} label={raw.label} commentable={false} />
            ) : (
              <p className="hint">発言や候補の「RAW を見る」を押すと、ここに出ます。</p>
            )}
          </details>
        </aside>
      )}
    </div>
  )
}
