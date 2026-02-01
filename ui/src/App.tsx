import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { LogsPanel } from './components/LogsPanel'
import { Dashboard } from './pages/Dashboard'
import { Analyze } from './pages/Analyze'
import { Stats } from './pages/Stats'

function App() {
  return (
    <>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/analyze" element={<Analyze />} />
          {/* Redirect old investigate URL to unified analyze page */}
          <Route path="/investigate" element={<Navigate to="/analyze" replace />} />
          <Route path="/stats" element={<Stats />} />
        </Routes>
      </Layout>
      <LogsPanel />
    </>
  )
}

export default App
