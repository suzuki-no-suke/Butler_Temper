import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { api, type BotDetail } from '../api'
import { fromDraft, toDraft, type SettingsDraft } from '../settingsForm'

export default function BotDetailPage() {
  const botId = Number(useParams().botId)
  const [bot, setBot] = useState<BotDetail | null>(null)
  // 画面上の「編集中の設定」。保存するまで DB には書かない
  const [draft, setDraft] = useState<SettingsDraft | null>(null)
  const [baseVersion, setBaseVersion] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [viewing, setViewing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    api.bot(botId).then(
      (b) => {
        setBot(b)
        const latest = b.versions.at(-1)
        if (latest) {
          setDraft(toDraft(latest.settings))
          setBaseVersion(latest.version)
        }
      },
      (e: Error) => setError(e.message),
    )
  }, [botId])

  if (!bot) return <div className="page">{error ? <p className="error">{error}</p> : '読み込み中…'}</div>

  const loadVersion = (version: number) => {
    const v = bot.versions.find((x) => x.version === version)
    if (!v) return
    setDraft(toDraft(v.settings))
    setBaseVersion(v.version)
    setMessage(`バージョン ${v.version} を編集中の設定に読み込みました（まだ保存していません）`)
  }

  const save = async () => {
    if (!draft) return
    setError(null)
    setMessage(null)
    const parsed = fromDraft(draft)
    if (!parsed.ok) {
      setError(parsed.error)
      return
    }
    try {
      const v = await api.createVersion(bot.id, { settings: parsed.settings, note })
      setBot(await api.bot(bot.id))
      setBaseVersion(v.version)
      setNote('')
      setMessage(`バージョン ${v.version} として保存しました`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const viewed = bot.versions.find((v) => v.version === viewing)

  return (
    <div className="page bot-detail">
      <h2>{bot.name}</h2>
      <dl className="bot-meta">
        <dt>プロバイダー</dt>
        <dd>{bot.provider}</dd>
        <dt>モデル（変更不可）</dt>
        <dd>
          <code>{JSON.stringify(bot.models)}</code>
        </dd>
        {bot.unavailable_reason && (
          <>
            <dt>状態</dt>
            <dd className="error">停止中: {bot.unavailable_reason}</dd>
          </>
        )}
      </dl>

      <div className="bot-columns">
        <section>
          <h3>編集中の設定（元: バージョン {baseVersion}）</h3>
          {error && <p className="error">{error}</p>}
          {message && <p className="notice">{message}</p>}
          {draft && (
            <div className="form">
              <label>
                システムプロンプト
                <textarea
                  value={draft.systemPrompt}
                  onChange={(e) => setDraft({ ...draft, systemPrompt: e.target.value })}
                  rows={14}
                />
              </label>
              <label>
                その他の設定（JSON。params は API にそのまま渡す）
                <textarea
                  className="code"
                  value={draft.restJson}
                  onChange={(e) => setDraft({ ...draft, restJson: e.target.value })}
                  rows={10}
                />
              </label>
              <label>
                変更メモ
                <input value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <button type="button" onClick={save}>
                新しいバージョンとして保存
              </button>
            </div>
          )}
        </section>

        <section>
          <h3>バージョン</h3>
          <ul className="version-list">
            {[...bot.versions].reverse().map((v) => (
              <li key={v.id}>
                <strong>v{v.version}</strong> {new Date(v.created_at).toLocaleString('ja-JP')}
                {v.note && <span> — {v.note}</span>}
                <div>
                  <button type="button" className="link" onClick={() => setViewing(v.version)}>
                    表示
                  </button>
                  <button type="button" className="link" onClick={() => loadVersion(v.version)}>
                    編集中の設定に読み込む
                  </button>
                </div>
              </li>
            ))}
          </ul>
          {viewed && (
            <>
              <h4>バージョン {viewed.version} の内容</h4>
              <pre className="code">{JSON.stringify(viewed.settings, null, 2)}</pre>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
