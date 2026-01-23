import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { LogsPanel } from './components/LogsPanel'
import { Dashboard } from './pages/Dashboard'
import { Analyze } from './pages/Analyze'
import { Investigate } from './pages/Investigate'
import { Stats } from './pages/Stats'

function App() {
  return (
    <>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/investigate" element={<Investigate />} />
          <Route path="/stats" element={<Stats />} />
        </Routes>
      </Layout>
      <LogsPanel />
    </>
  )
}

export default App
