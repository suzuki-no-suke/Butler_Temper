import { useCallback, useEffect, useState } from 'react'
import { NavLink, useParams } from 'react-router'
import { api, type SimulationRun, type Simulator } from '../api'
import SimulationSettingsEditor from '../components/SimulationSettingsEditor'
import { KIND_LABEL, STATUS_LABEL } from '../simulationLabels'

const json = (value: unknown) => JSON.stringify(value, null, 2)

type SchemaProperty = { type?: string }

// 必須の項目の入力欄の初期値。型に合わせた空の値にする
function emptyValue(property: SchemaProperty | undefined): unknown {
  switch (property?.type) {
    case 'integer':
    case 'number':
      return 1
    case 'array':
      return []
    case 'object':
      return {}
    default:
      return ''
  }
}

// 引数の入力欄の初期値。必須の項目は空の値、任意の項目は既定値を入れ、すべての項目を明示する
function initialArgs(s: Simulator): string {
  const properties = (s.input_schema.properties ?? {}) as Record<string, SchemaProperty>
  const args: Record<string, unknown> = {}
  for (const p of s.params) {
    if (p.kind === 'required') args[p.name] = emptyValue(properties[p.name])
    else if (p.kind === 'optional') args[p.name] = p.default
  }
  return json(args)
}

// シミュレータの一覧・グローバル設定・テスト実行・引数の提案。テスト実行は WebUI として記録される
export default function SimulatorsPage() {
  const { simulatorName } = useParams()
  const [simulators, setSimulators] = useState<Simulator[]>([])
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    api.simulators().then(setSimulators, (e: Error) => setError(e.message))
  }, [])

  useEffect(reload, [reload])

  const simulator = simulators.find((s) => s.name === simulatorName) ?? simulators[0] ?? null

  return (
    <div className="bots-layout">
      <aside className="sidebar">
        <h3>シミュレータ</h3>
        {error && <p className="error">{error}</p>}
        <ul className="bot-list">
          {simulators.map((s) => (
            <li key={s.name}>
              <NavLink
                to={`/simulators/${s.name}`}
                className={s.name === simulator?.name ? 'active' : ''}
              >
                {s.label}
                <small>{s.name}</small>
              </NavLink>
            </li>
          ))}
        </ul>
      </aside>
      <div className="page">
        <SimulationSettingsEditor onSaved={reload} />
        {simulator && <SimulatorView key={simulator.name} simulator={simulator} />}
      </div>
    </div>
  )
}

function SimulatorView({ simulator }: { simulator: Simulator }) {
  const [args, setArgs] = useState(() => initialArgs(simulator))
  const [times, setTimes] = useState(1)
  const [running, setRunning] = useState(false)
  const [runs, setRuns] = useState<SimulationRun[]>([])
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setError(null)
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(args) as Record<string, unknown>
    } catch {
      setError('引数が JSON として読めません')
      return
    }
    setRunning(true)
    try {
      setRuns(await api.testRunSimulator(simulator.name, parsed, times))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <>
      <h2>
        {simulator.label} <small className="code">{simulator.name}</small>
      </h2>
      <p>{simulator.description}</p>
      <p className="hint">結果の形式: {simulator.result_description}</p>
      <h3>項目</h3>
      {simulator.params.length === 0 ? (
        <p className="hint">項目はありません。</p>
      ) : (
        <ul>
          {simulator.params.map((p) => (
            <li key={p.name}>
              <span className="code">{p.name}</span>（{KIND_LABEL[p.kind]}
              {p.kind === 'optional' && p.global_key && `。既定はグローバル設定の ${p.global_key}`}
              ）: {p.description}
            </li>
          ))}
        </ul>
      )}
      <div className="bot-columns">
        <div>
          <h3>テスト実行</h3>
          <div className="form">
            <label>
              引数（JSON。任意の項目には既定値を入れてある）
              <textarea
                className="code"
                rows={Math.max(4, args.split('\n').length + 1)}
                value={args}
                onChange={(e) => setArgs(e.target.value)}
              />
            </label>
            <div className="button-row">
              <button type="button" className="secondary" onClick={() => setArgs(initialArgs(simulator))}>
                既定値に戻す
              </button>
            </div>
            <label>
              実行する回数（シミュレーション全体を続けて何回行うか）
              <input
                type="number"
                min={1}
                max={20}
                value={times}
                onChange={(e) => setTimes(Number(e.target.value))}
              />
            </label>
            <div className="button-row">
              <button type="button" onClick={run} disabled={running}>
                {running ? '実行中…' : '実行する'}
              </button>
            </div>
            {simulator.name === 'llm' && (
              <p className="hint">
                LLM シミュレータは、1 回の実行で LLM を（回数 + 1）回呼びます。費用がかかります。
              </p>
            )}
          </div>
          {error && <p className="error">{error}</p>}
          <ul className="history-list">
            {runs.map((r) => (
              <li key={r.id} className="history-item">
                <div className="history-head">
                  <NavLink to={`/simulation-runs/${r.id}`}>#{r.id}</NavLink>
                  <span className={`badge${r.status === 'succeeded' ? '' : ' error'}`}>
                    {STATUS_LABEL[r.status]}
                  </span>
                  {r.error_count > 0 && (
                    <span className="badge error">エラー {r.error_count} 回</span>
                  )}
                </div>
                {r.result && <pre className="code">{json(r.result)}</pre>}
                {r.error && <p className="error">{r.error}</p>}
              </li>
            ))}
          </ul>
        </div>
        <ArgsProposer simulator={simulator} currentArgs={args} onApply={(a) => setArgs(json(a))} />
      </div>
    </>
  )
}

interface ProposerLine {
  role: 'user' | 'assistant'
  content: string
  args?: Record<string, unknown> | null
}

// 要望から、シミュレータにそのまま渡せる引数を LLM が提案する。やり取りは保存しない
function ArgsProposer({
  simulator,
  currentArgs,
  onApply,
}: {
  simulator: Simulator
  currentArgs: string
  onApply: (args: Record<string, unknown>) => void
}) {
  const [lines, setLines] = useState<ProposerLine[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const send = async () => {
    const request = input.trim()
    if (request === '') return
    setError(null)
    setSending(true)
    try {
      const proposal = await api.proposeSimulatorArgs(simulator.name, {
        request,
        history: lines.map((l) => ({ role: l.role, content: l.content })),
        current_args: currentArgs,
      })
      setLines([
        ...lines,
        { role: 'user', content: request },
        { role: 'assistant', content: proposal.reply, args: proposal.args },
      ])
      setInput('')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="settings-chat">
      <h3>引数の提案</h3>
      <p className="hint">
        要望を書くと、このシミュレータにそのまま渡せる引数を LLM が提案します（既定値の項目も含めます）。
        Agent 設定やプロンプトに貼り付けて使えます。やり取りは保存しません。
      </p>
      <ol className="messages">
        {lines.map((l, i) => (
          <li key={i} className={`message ${l.role}`}>
            <div className="message-role">{l.role === 'user' ? 'あなた' : '提案'}</div>
            <div className="message-content">{l.content}</div>
            {l.args && (
              <>
                <pre className="code">{json(l.args)}</pre>
                <button type="button" className="secondary" onClick={() => onApply(l.args!)}>
                  テスト実行の入力欄に入れる
                </button>
              </>
            )}
          </li>
        ))}
      </ol>
      <div className="form">
        <textarea
          rows={3}
          placeholder="例: Hero が AA、BB が KK、フロップ 7s7h7d で 100 回"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <div className="button-row">
          <button type="button" onClick={send} disabled={sending || input.trim() === ''}>
            {sending ? '提案中…' : '提案してもらう'}
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  )
}
