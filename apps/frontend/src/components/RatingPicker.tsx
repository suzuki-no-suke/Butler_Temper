import { RATINGS, type Rating } from '../api'

interface Props {
  value: Rating | null
  onChange: (rating: Rating | null) => void
  // true なら、選んでいる評価をもう一度押すと選択を外せる
  allowNone?: boolean
}

export default function RatingPicker({ value, onChange, allowNone = false }: Props) {
  return (
    <div className="rating-picker" role="group" aria-label="評価">
      {RATINGS.map((r) => (
        <button
          key={r}
          type="button"
          className={`rating rating-${r.toLowerCase()}${value === r ? ' selected' : ''}`}
          aria-pressed={value === r}
          onClick={() => onChange(allowNone && value === r ? null : r)}
        >
          {r}
        </button>
      ))}
    </div>
  )
}
