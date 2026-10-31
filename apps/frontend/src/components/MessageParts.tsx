import { Link } from 'react-router'
import type { MessagePart } from '../api'

const PART_LABEL: Record<string, string> = {
  main: 'Agent（メイン）',
  sub: 'Agent（サブ）',
  system: 'システム',
  simulation: 'シミュレータ',
}

// Agent の発言の表示用の内訳（チャット・エージェント間対話・並行会話で共通）
export default function MessageParts({ parts }: { parts: MessagePart[] }) {
  return (
    <>
      {parts.map((p, i) => (
        <div key={i} className={`message assistant speaker-${p.speaker}`}>
          <div className="message-role">
            {PART_LABEL[p.speaker] ?? p.speaker}
            {p.secret && `：${p.secret}`}
          </div>
          <div className="message-content">{p.text}</div>
          {p.simulation_run_id != null && (
            <Link to={`/simulation-runs/${p.simulation_run_id}`}>
              実行記録 #{p.simulation_run_id} を見る
            </Link>
          )}
        </div>
      ))}
    </>
  )
}
