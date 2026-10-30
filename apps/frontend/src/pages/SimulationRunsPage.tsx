import { useEffect, useState } from 'react'
import { NavLink, useParams } from 'react-router'
import {
  api,
  type SimulationCaller,
  type SimulationRun,
  type SimulationRunDetail,
  type SimulationSettings,
  type Simulator,
} from '../api'
import { Exchange } from '../components/RawPanel'
import { CALLER_LABEL, STATUS_LABEL } from '../simulationLabels'

const json = (value: unknown) => JSON.stringify(value, null, 2)

const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString('ja-JP') : '—')

// 実行記録の呼び出し元。会話・対話へのリンクを付ける
function CallerView({ run }: { run: SimulationRun }) {
  return (
    <span>
      {CALLER_LABEL[run.caller]}
      {run.conversation_id !== null && (
        <>
          {' '}
          <NavLink to={`/chat/${run.conversation_id}`}>会話 #{run.conversation_id}</NavLink>
        </>
      )}
      {run.dialogue_id !== null && (
        <>
          {' '}
          <NavLink to={`/dialogue/${run.dialogue_id}`}>対話 #{run.dialogue_id}</NavLink>
        </>
      )}
      {run.agent_id && <span className="code">（{run.agent_id}）</span>}
    </span>
  )
}

// シミュレータの実行記録の一覧（Agent が呼んだもの・テスト実行を含む）と、グローバル設定
export default function SimulationRunsPage() {
  const { runId } = useParams()
  const [simulators, setSimulators] = useState<Simulator[]>([])
  const [simulator, setSimulator] = useState('')
  const [caller, setCaller] = useState('')
  const [runs, setRuns] = useState<SimulationRun[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.simulators().then(setSimulators, (e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    api.simulationRuns({ simulator, caller }).then(setRuns, (e: Error) => setError(e.message))
  }, [simulator, caller, runId])

  if (runId !== undefined) return <RunDetail key={runId} runId={Number(runId)} />

  return (
    <div className="page">
      <h2>シミュレーション履歴</h2>
      <GlobalSettingsEditor />
      <h3>実行記録</h3>
      <label className="filter">
        シミュレータで絞り込む
        <select value={simulator} onChange={(e) => setSimulator(e.target.value)}>
          <option value="">すべて</option>
          {simulators.map((s) => (
            <option key={s.name} value={s.name}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <label className="filter">
        呼び出し元で絞り込む
        <select value={caller} onChange={(e) => setCaller(e.target.value)}>
          <option value="">すべて</option>
          {(Object.keys(CALLER_LABEL) as SimulationCaller[]).map((c) => (
            <option key={c} value={c}>
              {CALLER_LABEL[c]}
            </option>
          ))}
        </select>
      </label>
      {error && <p className="error">{error}</p>}
      <ul className="history-list">
        {runs.map((r) => (
          <li key={r.id} className="history-item">
            <div className="history-head">
              <NavLink to={`/simulation-runs/${r.id}`}>
                <strong>#{r.id}</strong>
              </NavLink>
              <span className="code">{r.simulator}</span>
              <span className={`badge${r.status === 'succeeded' ? '' : ' error'}`}>
                {STATUS_LABEL[r.status]}
              </span>
              {r.error_count > 0 && <span className="badge error">エラー {r.error_count} 回</span>}
            </div>
            <div className="history-preview code">
              {json(r.args)} → {r.result ? json(r.result) : (r.error ?? '—')}
            </div>
            <div className="history-meta">
              <CallerView run={r} /> / {formatDate(r.started_at)}
            </div>
          </li>
        ))}
        {runs.length === 0 && <li className="hint">実行記録はまだありません。</li>}
      </ul>
    </div>
  )
}

function RunDetail({ runId }: { runId: number }) {
  const [run, setRun] = useState<SimulationRunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.simulationRun(runId).then(setRun, (e: Error) => setError(e.message))
  }, [runId])

  return (
    <div className="page">
      <p>
        <NavLink to="/simulation-runs">← シミュレーション履歴に戻る</NavLink>
      </p>
      {error && <p className="error">{error}</p>}
      {run && (
        <>
          <h2>
            実行記録 #{run.id} <span className="code">{run.simulator}</span>
          </h2>
          <div className="history-head">
            <span className={`badge${run.status === 'succeeded' ? '' : ' error'}`}>
              {STATUS_LABEL[run.status]}
            </span>
            {run.error_count > 0 && (
              <span className="badge error">エラー {run.error_count} 回</span>
            )}
          </div>
          <p className="history-meta">
            <CallerView run={run} /> / 開始 {formatDate(run.started_at)} / 終了{' '}
            {formatDate(run.finished_at)}
          </p>
          {run.error && <p className="error">{run.error}</p>}
          <h3>結果</h3>
          <pre className="code">{json(run.result)}</pre>
          <h3>呼び出しの引数</h3>
          <pre className="code">{json(run.args)}</pre>
          <h3>実行に使った値（グローバル設定の値を含む）</h3>
          <pre className="code">{json(run.params)}</pre>
          {run.detail && (
            <>
              <h3>内訳</h3>
              <pre className="code">{json(run.detail)}</pre>
            </>
          )}
          <h3>シミュレート用の RAW（{run.raw_calls.length} 件）</h3>
          {run.raw_calls.length === 0 && <p className="hint">LLM の呼び出しはありません。</p>}
          {run.raw_calls.map((raw) => (
            <div key={raw.id} className="raw-exchange">
              <div className="raw-exchange-head">
                <strong>{raw.label}</strong>
                {raw.error && <span className="error">{raw.error}</span>}
              </div>
              {raw.exchanges.map((ex, i) => (
                <Exchange key={i} exchange={ex} index={i} />
              ))}
            </div>
          ))}
        </>
      )}
    </div>
  )
}

// グローバル設定。バージョン管理はしない（実行のたびに、使った値が実行記録に残る）
function GlobalSettingsEditor() {
  const [settings, setSettings] = useState<SimulationSettings | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    api.simulationSettings().then((s) => {
      setSettings(s)
      setText(json(s.values))
    }, (e: Error) => setError(e.message))
  }, [])

  const save = async () => {
    setError(null)
    setMessage(null)
    let values: Record<string, unknown>
    try {
      values = JSON.parse(text) as Record<string, unknown>
    } catch {
      setError('JSON として読めません')
      return
    }
    try {
      const saved = await api.saveSimulationSettings(values)
      setSettings(saved)
      setText(json(saved.values))
      setMessage('保存しました')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <details className="agent-info">
      <summary>グローバル設定（GlobalSimulatingParameter）</summary>
      {settings && (
        <ul>
          {Object.entries(settings.descriptions).map(([key, description]) => (
            <li key={key}>
              <span className="code">{key}</span>: {description}（既定 {json(settings.defaults[key])}）
            </li>
          ))}
        </ul>
      )}
      <div className="form">
        <textarea
          className="code"
          rows={Math.max(6, text.split('\n').length + 1)}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="button-row">
          <button type="button" onClick={save}>
            保存する
          </button>
        </div>
        {message && <p className="notice">{message}</p>}
        {error && <p className="error">{error}</p>}
      </div>
    </details>
  )
}
