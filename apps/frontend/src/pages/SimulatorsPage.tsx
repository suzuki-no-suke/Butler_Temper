import { useEffect, useState } from 'react'
import { NavLink, useParams } from 'react-router'
import { api, type SimulationRun, type Simulator } from '../api'
import { KIND_LABEL, STATUS_LABEL } from '../simulationLabels'

const json = (value: unknown) => JSON.stringify(value, null, 2)

// 引数の入力欄の初期値。必須の項目だけを、型に合わせた空の値で並べる
function initialArgs(s: Simulator): string {
  const properties = (s.input_schema.properties ?? {}) as Record<string, { type?: string }>
  const args: Record<string, unknown> = {}
  for (const p of s.params) {
    if (p.kind !== 'required') continue
    args[p.name] = properties[p.name]?.type === 'integer' ? 1 : ''
  }
  return json(args)
}

// シミュレータの一覧と、画面からのテスト実行。呼び出し元は WebUI（テスト実行）として記録される
export default function SimulatorsPage() {
  const { simulatorName } = useParams()
  const [simulators, setSimulators] = useState<Simulator[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.simulators().then(setSimulators, (e: Error) => setError(e.message))
  }, [])

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
      {simulator && <SimulatorView key={simulator.name} simulator={simulator} />}
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
    <div className="page">
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
      <h3>テスト実行</h3>
      <div className="form">
        <label>
          引数（JSON）
          <textarea
            className="code"
            rows={Math.max(4, args.split('\n').length + 1)}
            value={args}
            onChange={(e) => setArgs(e.target.value)}
          />
        </label>
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
              {r.error_count > 0 && <span className="badge error">エラー {r.error_count} 回</span>}
            </div>
            {r.result && <pre className="code">{json(r.result)}</pre>}
            {r.error && <p className="error">{r.error}</p>}
          </li>
        ))}
      </ul>
    </div>
  )
}
