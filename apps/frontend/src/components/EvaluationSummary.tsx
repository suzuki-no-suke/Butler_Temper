import { RATINGS, type MessageComment } from '../api'

interface Rated {
  id: number
  seq: number
  content: string
  comment: MessageComment | null
}

interface Props<T extends Rated> {
  messages: T[]
  // 発言を選び、RAW パラメーター欄に表示する
  onSelect: (messageId: number) => void
  // 発言者の表示。指定すると、一覧の各行に添える
  speakerLabel?: (message: T) => string
  title?: string
}

const PREVIEW_CHARS = 40

// この会話で、ここまでに発言へ付けた評価とコメントの一覧
export default function EvaluationSummary<T extends Rated>({
  messages,
  onSelect,
  speakerLabel,
  title = '回答への評価とコメント（ここまで）',
}: Props<T>) {
  const rated = messages.filter((m) => m.comment)
  const counts = RATINGS.map((r) => [r, rated.filter((m) => m.comment?.rating === r).length] as const)

  return (
    <section className="evaluation-summary">
      <h3>{title}</h3>
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
                  発言 #{m.seq + 1}{speakerLabel && `（${speakerLabel(m)}）`}「
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
