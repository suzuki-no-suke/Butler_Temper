import { HashRouter, NavLink, Navigate, Route, Routes } from 'react-router'
import BotDetailPage from './pages/BotDetailPage'
import BotsPage from './pages/BotsPage'
import ChatPage from './pages/ChatPage'

export default function App() {
  return (
    <HashRouter>
      <header className="app-header">
        <span className="app-title">Butler Temper</span>
        <nav>
          <NavLink to="/chat">チャット</NavLink>
          <NavLink to="/bots">BOT 設定</NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
          <Route path="/bots" element={<BotsPage />} />
          <Route path="/bots/:botId" element={<BotDetailPage />} />
        </Routes>
      </main>
    </HashRouter>
  )
}
