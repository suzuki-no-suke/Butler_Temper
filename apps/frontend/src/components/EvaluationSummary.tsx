import { RATINGS, type Message } from '../api'

interface Props {
  messages: Message[]
  // 発言を選び、RAW パラメーター欄に表示する
  onSelect: (messageId: number) => void
}

const PREVIEW_CHARS = 40

// この会話で、ここまでに Agent の回答へ付けた評価とコメントの一覧
export default function EvaluationSummary({ messages, onSelect }: Props) {
  const rated = messages.filter((m) => m.comment)
  const counts = RATINGS.map((r) => [r, rated.filter((m) => m.comment?.rating === r).length] as const)

  return (
    <section className="evaluation-summary">
      <h3>回答への評価とコメント（ここまで）</h3>
      {rated.length === 0 ? (
        <p className="hint">まだありません。</p>
      ) : (
        <>
          <p className="evaluation-counts">
            {counts.map(([r, n]) => (
              <span key={r}>
                <span className={`rating-badge rating-${r.toLowerCase()}`}>{r}</span>
                {n} 件
              </span>
            ))}
          </p>
          <ul>
            {rated.map((m) => (
              <li key={m.id}>
                <span className={`rating-badge rating-${m.comment!.rating.toLowerCase()}`}>
                  {m.comment!.rating}
                </span>
                <span className="evaluation-target">
                  発言 #{m.seq + 1}「
                  {m.content.length > PREVIEW_CHARS
                    ? `${m.content.slice(0, PREVIEW_CHARS)}…`
                    : m.content}
                  」
                </span>
                {m.comment!.text && <span className="comment-text">{m.comment!.text}</span>}
                <button type="button" className="link" onClick={() => onSelect(m.id)}>
                  RAW で見る
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
