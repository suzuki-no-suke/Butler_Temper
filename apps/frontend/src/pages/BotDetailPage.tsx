import { useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext, useParams } from 'react-router'
import { api, type BotDetail } from '../api'
import AgentInfo from '../components/AgentInfo'
import SettingsChat from '../components/SettingsChat'
import { formatSettings, parseSettings } from '../settingsJson'
import type { BotsContext } from './BotsLayout'

export default function BotDetailPage() {
  const botId = Number(useParams().botId)
  const { agents, reloadBots } = useOutletContext<BotsContext>()
  const navigate = useNavigate()
  const [bot, setBot] = useState<BotDetail | null>(null)
  const [name, setName] = useState('')
  // 画面上の「編集中の設定」。保存するまで DB には書かない
  const [draft, setDraft] = useState('')
  const [baseVersion, setBaseVersion] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [viewing, setViewing] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    api.bot(botId).then(
      (b) => {
        setBot(b)
        setName(b.name)
        setViewing(null)
        setMessage(null)
        setError(null)
        const latest = b.versions.at(-1)
        if (latest) {
          setDraft(formatSettings(latest.settings))
          setBaseVersion(latest.version)
        }
      },
      (e: Error) => setError(e.message),
    )
  }, [botId])

  if (!bot) return <div className="page">{error ? <p className="error">{error}</p> : '読み込み中…'}</div>

  const agent = agents.find((a) => a.id === bot.agent_id)

  const loadVersion = (version: number) => {
    const v = bot.versions.find((x) => x.version === version)
    if (!v) return
    setDraft(formatSettings(v.settings))
    setBaseVersion(v.version)
    setMessage(`バージョン ${v.version} を編集中の設定に読み込みました（まだ保存していません）`)
  }

  const loadDefault = () => {
    if (!agent) return
    setDraft(formatSettings(agent.default_settings))
    setBaseVersion(null)
    setMessage('AgentCore の既定の Agent 設定を編集中の設定に読み込みました（まだ保存していません）')
  }

  const save = async () => {
    setError(null)
    setMessage(null)
    const parsed = parseSettings(draft)
    if (!parsed.ok) {
      setError(parsed.error)
      return
    }
    if (forking) {
      try {
        const forked = await api.forkBot(bot.id, {
          name: name.trim(),
          settings: parsed.settings,
          note,
          base_version: baseVersion,
        })
        reloadBots()
        setNote('')
        navigate(`/bots/${forked.id}`)
      } catch (e) {
        setError((e as Error).message)
      }
      return
    }
    try {
      const v = await api.createVersion(bot.id, { settings: parsed.settings, note })
      setBot(await api.bot(bot.id))
      reloadBots()
      setBaseVersion(v.version)
      setNote('')
      setMessage(`バージョン ${v.version} として保存しました`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const viewed = bot.versions.find((v) => v.version === viewing)
  // 名前を変えて保存すると、新しい Agent として分かれる（フォーク）
  const forking = name.trim() !== '' && name.trim() !== bot.name

  return (
    <div className="page bot-detail">
      <div className="name-row">
        <input value={name} onChange={(e) => setName(e.target.value)} aria-label="名前" />
        {forking && (
          <button type="button" className="link" onClick={() => setName(bot.name)}>
            名前を元に戻す
          </button>
        )}
      </div>
      <p className="hint">
        名前を変えずに保存すると、同じ名前の Agent の新しいバージョンになります。
        名前を変えて保存すると、この Agent はそのままに、同じ AgentCore で新しい名前の Agent を v1
        から作ります（フォーク。バージョンの履歴と会話は引き継ぎません）。
      </p>
      {bot.forked_from_bot_id && (
        <p className="hint">
          <Link to={`/bots/${bot.forked_from_bot_id}`}>
            {bot.forked_from_bot_name ?? `Agent #${bot.forked_from_bot_id}`}
          </Link>
          {bot.forked_from_version !== null && ` のバージョン ${bot.forked_from_version}`}
          からフォークした Agent です。
        </p>
      )}
      {bot.unavailable_reason && <p className="error">停止中: {bot.unavailable_reason}</p>}
      {agent ? <AgentInfo agent={agent} /> : <p className="error">{bot.agent_name}</p>}

      <div className="bot-columns">
        <section>
          <h3>
            編集中の設定（元: {baseVersion === null ? 'AgentCore の既定の Agent 設定' : `バージョン ${baseVersion}`}）
          </h3>
          {error && <pre className="error">{error}</pre>}
          {message && <p className="notice">{message}</p>}
          <div className="form">
            <label>
              Agent 設定（JSON）
              <textarea
                className="code"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={28}
              />
            </label>
            <label>
              変更メモ
              <input value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
            <div className="button-row">
              <button type="button" onClick={save}>
                {forking ? `「${name.trim()}」としてフォークする` : '新しいバージョンとして保存'}
              </button>
              <button type="button" className="secondary" onClick={loadDefault} disabled={!agent}>
                既定の Agent 設定を読み込む
              </button>
            </div>
          </div>
          <SettingsChat
            key={bot.id}
            botId={bot.id}
            currentSettings={draft}
            onProposal={(settings) => {
              setDraft(formatSettings(settings))
              setError(null)
              setMessage('設定変更チャットの案を編集中の設定に反映しました（まだ保存していません）')
            }}
          />
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
              <pre className="code">{formatSettings(viewed.settings)}</pre>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
