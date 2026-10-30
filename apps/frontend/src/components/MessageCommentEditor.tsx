import { useState } from 'react'
import { conversationCommentApi, type CommentApi, type MessageComment, type Rating } from '../api'
import RatingPicker from './RatingPicker'

interface Props {
  messageId: number
  comment: MessageComment | null
  onSaved: (comment: MessageComment | null) => void
  // 既定は Agent との会話の発言
  commentApi?: CommentApi
  // 評価を付けるボタンの文言
  label?: string
}

// 発言一つにつき一つの評価とコメント
export default function MessageCommentEditor({
  messageId,
  comment,
  onSaved,
  commentApi = conversationCommentApi,
  label = 'この回答を評価する',
}: Props) {
  const [editing, setEditing] = useState(false)
  const [rating, setRating] = useState<Rating | null>(comment?.rating ?? null)
  const [text, setText] = useState(comment?.text ?? '')
  const [error, setError] = useState<string | null>(null)

  const open = () => {
    setRating(comment?.rating ?? null)
    setText(comment?.text ?? '')
    setEditing(true)
  }

  const save = async () => {
    if (!rating) return
    setError(null)
    try {
      onSaved(await commentApi.putMessageComment(messageId, rating, text))
      setEditing(false)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const remove = async () => {
    setError(null)
    try {
      await commentApi.deleteMessageComment(messageId)
      onSaved(null)
      setEditing(false)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!editing) {
    return (
      <div className="message-comment">
        {comment ? (
          <>
            <span className={`rating-badge rating-${comment.rating.toLowerCase()}`}>
              {comment.rating}
            </span>
            {comment.text && <span className="comment-text">{comment.text}</span>}
            <button type="button" className="link" onClick={open}>
              評価を直す
            </button>
          </>
        ) : (
          <button type="button" className="link" onClick={open}>
            {label}
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="message-comment editing">
      <RatingPicker value={rating} onChange={setRating} />
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        placeholder="コメント（任意）"
        aria-label="回答へのコメント"
      />
      {error && <p className="error">{error}</p>}
      <div className="button-row">
        <button type="button" onClick={save} disabled={!rating}>
          保存
        </button>
        <button type="button" className="secondary" onClick={() => setEditing(false)}>
          やめる
        </button>
        {comment && (
          <button type="button" className="link" onClick={remove}>
            評価を消す
          </button>
        )}
      </div>
    </div>
  )
}
