import { HashRouter, NavLink, Navigate, Route, Routes } from 'react-router'
import BotDetailPage from './pages/BotDetailPage'
import BotNewPage from './pages/BotNewPage'
import { AGENT_KIND, CONVERSATION_KIND } from './botKinds'
import BotsLayout from './pages/BotsLayout'
import ChatPage from './pages/ChatPage'
import DialogueHistoryPage from './pages/DialogueHistoryPage'
import DialoguePage from './pages/DialoguePage'
import HistoryPage from './pages/HistoryPage'
import ParallelPage from './pages/ParallelPage'
import ParallelSettingsPage from './pages/ParallelSettingsPage'
import SimulationRunsPage from './pages/SimulationRunsPage'
import SimulatorsPage from './pages/SimulatorsPage'
import TemplatesPage from './pages/TemplatesPage'
import { AGENT_TEMPLATE_KIND, DIALOGUE_TEMPLATE_KIND } from './templateKinds'

export default function App() {
  return (
    <HashRouter>
      <header className="app-header">
        <span className="app-title">Butler Temper</span>
        <nav>
          <NavLink to="/chat">チャット</NavLink>
          <NavLink to="/history">履歴</NavLink>
          <NavLink to="/bots">Agent 設定</NavLink>
          <NavLink to="/agent-templates">Agent テンプレート</NavLink>
          <span className="nav-separator" />
          <NavLink to="/dialogue">エージェント間対話</NavLink>
          <NavLink to="/dialogue-history">対話履歴</NavLink>
          <NavLink to="/conversation-bots">会話用エージェント設定</NavLink>
          <NavLink to="/templates">対話用テンプレート</NavLink>
          <span className="nav-separator" />
          <NavLink to="/simulators">シミュレータ</NavLink>
          <NavLink to="/simulation-runs">シミュレーション履歴</NavLink>
          <span className="nav-separator" />
          <NavLink to="/parallel">並行会話</NavLink>
          <NavLink to="/parallel-settings">並行会話設定</NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/bots" element={<BotsLayout key="agent" kind={AGENT_KIND} />}>
            <Route index element={<p className="hint">左の一覧から Agent を選ぶか、新しい Agent を作ってください。</p>} />
            <Route path="new" element={<BotNewPage />} />
            <Route path=":botId" element={<BotDetailPage />} />
          </Route>
          <Route path="/dialogue" element={<DialoguePage />} />
          <Route path="/dialogue/:dialogueId" element={<DialoguePage />} />
          <Route path="/dialogue-history" element={<DialogueHistoryPage />} />
          <Route
            path="/conversation-bots"
            element={<BotsLayout key="conversation" kind={CONVERSATION_KIND} />}
          >
            <Route
              index
              element={
                <p className="hint">
                  左の一覧から会話用エージェントを選ぶか、新しい会話用エージェントを作ってください。
                </p>
              }
            />
            <Route path="new" element={<BotNewPage />} />
            <Route path=":botId" element={<BotDetailPage />} />
          </Route>
          <Route path="/templates" element={<TemplatesPage key="dialogue" kind={DIALOGUE_TEMPLATE_KIND} />} />
          <Route
            path="/templates/:templateId"
            element={<TemplatesPage key="dialogue" kind={DIALOGUE_TEMPLATE_KIND} />}
          />
          <Route
            path="/agent-templates"
            element={<TemplatesPage key="agent" kind={AGENT_TEMPLATE_KIND} />}
          />
          <Route
            path="/agent-templates/:templateId"
            element={<TemplatesPage key="agent" kind={AGENT_TEMPLATE_KIND} />}
          />
          <Route path="/simulators" element={<SimulatorsPage />} />
          <Route path="/simulators/:simulatorName" element={<SimulatorsPage />} />
          <Route path="/simulation-runs" element={<SimulationRunsPage />} />
          <Route path="/simulation-runs/:runId" element={<SimulationRunsPage />} />
          <Route path="/parallel" element={<ParallelPage />} />
          <Route path="/parallel/:parallelId" element={<ParallelPage />} />
          <Route path="/parallel-settings" element={<ParallelSettingsPage />} />
        </Routes>
      </main>
    </HashRouter>
  )
}
