import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'

// 並行会話の設定。シミュレータのグローバル設定とは別に持つ
export default function ParallelSettingsPage() {
  const [concurrency, setConcurrency] = useState<number | null>(null)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.parallelSettings().then(
      (s) => setConcurrency(s.concurrency),
      (e: Error) => setError(e.message),
    )
  }, [])

  const save = async (e: FormEvent) => {
    e.preventDefault()
    if (concurrency === null) return
    setError(null)
    setSaved(false)
    try {
      const s = await api.saveParallelSettings({ concurrency })
      setConcurrency(s.concurrency)
      setSaved(true)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <section className="page">
      <h2>並行会話設定</h2>
      {error && <p className="error">{error}</p>}
      {concurrency !== null && (
        <form onSubmit={save}>
          <label>
            候補を同時に作る数（1〜20）
            <input
              type="number"
              min={1}
              max={20}
              value={concurrency}
              onChange={(e) => {
                setConcurrency(Number(e.target.value))
                setSaved(false)
              }}
            />
          </label>
          <button type="submit">保存</button>
          {saved && <span className="hint"> 保存しました</span>}
        </form>
      )}
      <p className="hint">
        API の提供元ごとの同時実行の制限は扱いません。制限に当たってエラーになるときは、この数を下げてください。
      </p>
    </section>
  )
}
