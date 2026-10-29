import { HashRouter, NavLink, Navigate, Route, Routes } from 'react-router'
import BotDetailPage from './pages/BotDetailPage'
import BotNewPage from './pages/BotNewPage'
import BotsLayout from './pages/BotsLayout'
import ChatPage from './pages/ChatPage'
import HistoryPage from './pages/HistoryPage'

export default function App() {
  return (
    <HashRouter>
      <header className="app-header">
        <span className="app-title">Butler Temper</span>
        <nav>
          <NavLink to="/chat">チャット</NavLink>
          <NavLink to="/history">履歴</NavLink>
          <NavLink to="/bots">BOT 設定</NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/bots" element={<BotsLayout />}>
            <Route index element={<p className="hint">左の一覧から BOT を選ぶか、新しい BOT を作ってください。</p>} />
            <Route path="new" element={<BotNewPage />} />
            <Route path=":botId" element={<BotDetailPage />} />
          </Route>
        </Routes>
      </main>
    </HashRouter>
  )
}
