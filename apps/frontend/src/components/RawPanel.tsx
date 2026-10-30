import { useEffect, useState } from 'react'
import { api, type MessageComment, type RawCall, type RawExchange } from '../api'

const json = (value: unknown) => JSON.stringify(value, null, 2)

const time = (iso?: string | null) => (iso ? new Date(iso).toLocaleTimeString('ja-JP') : '—')

function Exchange({ exchange, index }: { exchange: RawExchange; index: number }) {
  return (
    <div className="raw-exchange">
      <div className="raw-exchange-head">
        <strong>
          {index + 1}. {exchange.label ?? '（ラベルなし）'}
        </strong>
        <span className={exchange.status && exchange.status >= 400 ? 'error' : ''}>
          {exchange.status ?? '応答なし'}
        </span>
      </div>
      <div className="raw-meta">
        {exchange.method} {exchange.url}
        <br />
        送信 {time(exchange.sent_at)} / 受信 {time(exchange.received_at)}
      </div>
      <details>
        <summary>リクエスト</summary>
        <pre className="code">{json(exchange.request)}</pre>
      </details>
      <details>
        <summary>レスポンス</summary>
        <pre className="code">{json(exchange.response)}</pre>
      </details>
      {(exchange.request_headers || exchange.response_headers) && (
        <details>
          <summary>ヘッダー（API キーは記録していない）</summary>
          <pre className="code">
            {json({ request: exchange.request_headers, response: exchange.response_headers })}
          </pre>
        </details>
      )}
    </div>
  )
}

// RAW パラメーター欄に出せる発言（Agent との会話と、エージェント間対話の両方）
export interface RawTarget {
  seq: number
  raw_call_id: number | null
  agent_state: Record<string, unknown> | null
  parts: unknown[] | null
  comment: MessageComment | null
}

interface Props {
  message: RawTarget | null
  // 発言者の表示（例: Agent / エラー）
  label: string
  // 評価・コメントを付けられる発言か
  commentable: boolean
}

// 選んだ発言の RAW（LLM とのやり取り）と、Agent が残した記録を表示する
export default function RawPanel({ message, label, commentable }: Props) {
  const [raw, setRaw] = useState<RawCall | null>(null)
  const [error, setError] = useState<string | null>(null)
  const rawCallId = message?.raw_call_id ?? null

  useEffect(() => {
    if (rawCallId === null) return
    let cancelled = false
    api.rawCall(rawCallId).then(
      (r) => {
        if (!cancelled) {
          setRaw(r)
          setError(null)
        }
      },
      (e: Error) => {
        if (!cancelled) setError(e.message)
      },
    )
    return () => {
      cancelled = true
    }
  }, [rawCallId])

  if (!message || rawCallId === null) {
    return <p className="hint">RAW のある発言がまだありません。</p>
  }
  const shown = raw?.id === rawCallId ? raw : null

  return (
    <div className="raw-panel-body">
      <p className="hint">発言 #{message.seq + 1}（{label}）の記録</p>
      {error && <p className="error">{error}</p>}

      {commentable && (
        <details open>
          <summary>この発言への評価・コメント</summary>
          {message.comment ? (
            <p className="raw-comment">
              <span className={`rating-badge rating-${message.comment.rating.toLowerCase()}`}>
                {message.comment.rating}
              </span>
              <span className="comment-text">{message.comment.text || '（コメントなし）'}</span>
              <br />
              <small>{new Date(message.comment.updated_at).toLocaleString('ja-JP')}</small>
            </p>
          ) : (
            <p className="hint">まだ評価していません</p>
          )}
        </details>
      )}

      <details open>
        <summary>Agent の状態（このターンの後）</summary>
        {message.agent_state && Object.keys(message.agent_state).length > 0 ? (
          <pre className="code">{json(message.agent_state)}</pre>
        ) : (
          <p className="hint">記録なし</p>
        )}
      </details>
      {message.parts && (
        <details>
          <summary>表示用の内訳（parts）</summary>
          <pre className="code">{json(message.parts)}</pre>
        </details>
      )}

      {!shown && !error && <p className="hint">読み込み中…</p>}
      {shown && (
        <>
          <details open>
            <summary>呼び出しの概要</summary>
            <dl className="raw-summary">
              <dt>AgentCore</dt>
              <dd>
                <code>{shown.agent_id}</code>
              </dd>
              <dt>開始〜終了</dt>
              <dd>
                {time(shown.started_at)} 〜 {time(shown.finished_at)}
              </dd>
              <dt>ソースのハッシュ</dt>
              <dd>
                <code title={shown.source_hash}>{shown.source_hash.slice(0, 12)}…</code>
              </dd>
              <dt>呼び出し数</dt>
              <dd>{shown.exchanges.length}</dd>
            </dl>
            {shown.error && <pre className="error">{shown.error}</pre>}
          </details>
          <h4>LLM とのやり取り</h4>
          {shown.exchanges.length === 0 && <p className="hint">通信していません</p>}
          {shown.exchanges.map((ex, i) => (
            <Exchange key={i} exchange={ex} index={i} />
          ))}
        </>
      )}
    </div>
  )
}
