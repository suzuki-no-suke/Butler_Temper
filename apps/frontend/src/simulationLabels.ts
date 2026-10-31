// シミュレータの画面で使う表示名
import type { SimulationCaller, SimulationRun, SimulatorParam } from './api'

export const KIND_LABEL: Record<SimulatorParam['kind'], string> = {
  required: '必須',
  optional: '任意',
  global: '指定不可（グローバル設定）',
}

export const STATUS_LABEL: Record<SimulationRun['status'], string> = {
  succeeded: '成功',
  failed: '失敗',
  invalid: '引数が合わない',
}

export const CALLER_LABEL: Record<SimulationCaller, string> = {
  conversation: 'チャット',
  dialogue: 'エージェント間対話',
  webui: 'WebUI（テスト実行）',
  parallel: '並行会話の候補',
}
