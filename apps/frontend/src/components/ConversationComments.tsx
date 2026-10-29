import { useState } from 'react'
import { api, type ConversationComment, type Rating } from '../api'
import RatingPicker from './RatingPicker'

interface Props {
  conversationId: number
  comments: ConversationComment[]
  onChange: (comments: ConversationComment[]) => void
}

// 会話全体へのコメント。都度いくつでも付けられる
export default function ConversationComments({ conversationId, comments, onChange }: Props) {
  const [rating, setRating] = useState<Rating | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)

  const add = async () => {
    setError(null)
    try {
      const comment = await api.addConversationComment(conversationId, rating, text)
      onChange([...comments, comment])
      setRating(null)
      setText('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const remove = async (id: number) => {
    setError(null)
    try {
      await api.deleteConversationComment(id)
      onChange(comments.filter((c) => c.id !== id))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <section className="conversation-comments">
      <h3>会話全体へのコメント</h3>
      <ul>
        {comments.map((c) => (
          <li key={c.id}>
            {c.rating && (
              <span className={`rating-badge rating-${c.rating.toLowerCase()}`}>{c.rating}</span>
            )}
            <span className="comment-text">{c.text}</span>
            <small>{new Date(c.created_at).toLocaleString('ja-JP')}</small>
            <button type="button" className="link" onClick={() => remove(c.id)}>
              消す
            </button>
          </li>
        ))}
        {comments.length === 0 && <li className="hint">まだありません。</li>}
      </ul>
      <div className="form">
        <RatingPicker value={rating} onChange={setRating} allowNone />
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="コメント"
          aria-label="会話全体へのコメント"
        />
        {error && <p className="error">{error}</p>}
        <div className="button-row">
          <button type="button" onClick={add} disabled={!rating && text.trim() === ''}>
            コメントを追加
          </button>
        </div>
      </div>
    </section>
  )
}
