import { useCallback, useEffect, useState } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router'
import type { Template, TemplateDetail } from '../api'
import type { TemplateKind } from '../templateKinds'

// テンプレート（プロンプトに埋め込む文章）。対話用テンプレートと Agent テンプレートを kind で分ける。
// 名前は変えられず、保存するたびに新しいバージョンになる
export default function TemplatesPage({ kind }: { kind: TemplateKind }) {
  const { templateId } = useParams()
  const [templates, setTemplates] = useState<Template[]>([])
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    kind.list().then(setTemplates, (e: Error) => setError(e.message))
  }, [kind])

  useEffect(reload, [reload])

  return (
    <div className="bots-layout">
      <aside className="sidebar">
        <NavLink to={kind.basePath} end className="button">
          新しい{kind.label}を作る
        </NavLink>
        <h3>{kind.label}</h3>
        {error && <p className="error">{error}</p>}
        <ul className="bot-list">
          {templates.map((t) => (
            <li key={t.id}>
              <NavLink to={`${kind.basePath}/${t.id}`}>
                {t.name}
                <small>v{t.latest_version}</small>
              </NavLink>
            </li>
          ))}
          {templates.length === 0 && <li className="hint">まだありません</li>}
        </ul>
      </aside>
      <TemplateEditor
        kind={kind}
        key={templateId ?? 'new'}
        templateId={templateId === undefined ? null : Number(templateId)}
        onSaved={reload}
      />
    </div>
  )
}

// テンプレートを開くたびに作り直す（key で切り替える）
function TemplateEditor({
  kind,
  templateId,
  onSaved,
}: {
  kind: TemplateKind
  templateId: number | null
  onSaved: () => void
}) {
  const navigate = useNavigate()
  const [detail, setDetail] = useState<TemplateDetail | null>(null)
  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [note, setNote] = useState('')
  const [viewing, setViewing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const creating = templateId === null

  useEffect(() => {
    if (templateId === null) return
    kind.get(templateId).then(
      (t) => {
        setDetail(t)
        setContent(t.versions.at(-1)?.content ?? '')
      },
      (e: Error) => setError(e.message),
    )
  }, [kind, templateId])

  const save = async () => {
    setError(null)
    setMessage(null)
    try {
      if (creating) {
        const t = await kind.create({ name: name.trim(), content, note })
        onSaved()
        navigate(`${kind.basePath}/${t.id}`)
        return
      }
      if (!detail) return
      const v = await kind.createVersion(detail.id, { content, note })
      setDetail(await kind.get(detail.id))
      onSaved()
      setNote('')
      setMessage(`バージョン ${v.version} として保存しました`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const viewed = detail?.versions.find((v) => v.version === viewing)
  const placeholder = creating ? name.trim() || '名前' : detail?.name ?? ''

  return (
    <section className="page">
        {creating ? (
          <h2>新しい{kind.label}を作る</h2>
        ) : (
          <h2>{detail?.name ?? '読み込み中…'}</h2>
        )}
        <p className="hint">
          <code>{kind.placeholder(placeholder)}</code> の形で使います。{kind.usage}
          入れ子にはしません。保存するときに、改行とタブ以外の制御文字を取り除きます。
        </p>
        <div className="bot-columns">
          <section>
            {error && <pre className="error">{error}</pre>}
            {message && <p className="notice">{message}</p>}
            <div className="form">
              {creating && (
                <label>
                  名前（作成後は変えられません。<code>{'{'}</code> <code>{'}'}</code>{' '}
                  と改行は使えません）
                  <input value={name} onChange={(e) => setName(e.target.value)} />
                </label>
              )}
              <label>
                本文
                <textarea
                  className="code"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  rows={24}
                />
              </label>
              <label>
                変更メモ
                <input value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <div className="button-row">
                <button
                  type="button"
                  onClick={save}
                  disabled={creating ? name.trim() === '' : !detail}
                >
                  {creating ? '作成' : '新しいバージョンとして保存'}
                </button>
              </div>
            </div>
          </section>
          {detail && (
            <section>
              <h3>バージョン</h3>
              <ul className="version-list">
                {[...detail.versions].reverse().map((v) => (
                  <li key={v.id}>
                    <strong>v{v.version}</strong> {new Date(v.created_at).toLocaleString('ja-JP')}
                    {v.note && <span> — {v.note}</span>}
                    <div>
                      <button type="button" className="link" onClick={() => setViewing(v.version)}>
                        表示
                      </button>
                      <button
                        type="button"
                        className="link"
                        onClick={() => {
                          setContent(v.content)
                          setMessage(`バージョン ${v.version} を読み込みました（まだ保存していません）`)
                        }}
                      >
                        本文に読み込む
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
              {viewed && (
                <>
                  <h4>バージョン {viewed.version} の本文</h4>
                  <pre className="code">{viewed.content}</pre>
                </>
              )}
            </section>
          )}
        </div>
    </section>
  )
}
