import { useState } from 'react'
import { Microscope, Send, RotateCcw, ChevronDown, AlertTriangle } from 'lucide-react'
import { useInvestigate } from '../hooks/useInvestigate'
import { useHealth } from '../hooks/useHealth'
import { ResultCard } from '../components/ResultCard'
import { SummaryChart } from '../components/SummaryChart'
import { LoadingOverlay } from '../components/LoadingSpinner'
import { cn } from '../utils/cn'

export function Investigate() {
  const { data, loading, error, investigate, reset } = useInvestigate()
  const { health } = useHealth()
  
  const [launchId, setLaunchId] = useState('')
  const [component, setComponent] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [pushToRp, setPushToRp] = useState(false)
  const [verifyMode, setVerifyMode] = useState<'none' | 'run' | 'analyze-history'>('none')
  const [provider, setProvider] = useState('anthropic')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!launchId || !component) return

    await investigate({
      launch_id: launchId,
      component,
      push_to_rp: pushToRp,
      verify_mode: verifyMode,
      provider,
    })
  }

  const handleReset = () => {
    reset()
    setLaunchId('')
    setComponent('')
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Microscope className="h-7 w-7 text-purple-600" />
          Deep Investigation
        </h1>
        <p className="mt-1 text-gray-600">
          Thorough RCA using Thinker-Critic pattern for accurate root cause analysis
        </p>
      </div>

      <div className="card border-purple-200 bg-purple-50">
        <div className="p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-purple-600 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-purple-900">This uses more LLM tokens</p>
            <p className="text-purple-700">
              Deep investigation runs 3 LLM calls per failure (Thinker, Critic, Refiner). 
              Use Quick Analysis for faster results.
            </p>
          </div>
        </div>
      </div>

      <div className="card">
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label htmlFor="launchId" className="label">Launch ID</label>
              <input
                type="text"
                id="launchId"
                value={launchId}
                onChange={(e) => setLaunchId(e.target.value)}
                placeholder="e.g., 9657"
                className="input"
                required
              />
            </div>
            
            <div>
              <label htmlFor="component" className="label">Component</label>
              <input
                type="text"
                id="component"
                value={component}
                onChange={(e) => setComponent(e.target.value)}
                placeholder="e.g., Model_server"
                className="input"
                required
              />
            </div>
          </div>

          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
          >
            <ChevronDown className={cn("h-4 w-4 transition-transform", showAdvanced && "rotate-180")} />
            Advanced Options
          </button>

          {showAdvanced && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-4 rounded-lg bg-gray-50">
              <div>
                <label htmlFor="provider" className="label">LLM Provider</label>
                <select
                  id="provider"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  className="input"
                >
                  {(health?.llm_providers || ['claude-cli', 'anthropic', 'groq', 'ollama']).map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label htmlFor="verifyMode" className="label">Verification</label>
                <select
                  id="verifyMode"
                  value={verifyMode}
                  onChange={(e) => setVerifyMode(e.target.value as 'none' | 'run' | 'analyze-history')}
                  className="input"
                >
                  <option value="none">None</option>
                  <option value="run">Run Test (uv pytest)</option>
                  <option value="analyze-history">Analyze History</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {verifyMode === 'run' && 'Executes test using uv run pytest'}
                  {verifyMode === 'analyze-history' && 'Analyzes RP history + test code'}
                  {verifyMode === 'none' && 'No verification'}
                </p>
              </div>
              
              <label className="flex items-center gap-2 p-2">
                <input
                  type="checkbox"
                  checked={pushToRp}
                  onChange={(e) => setPushToRp(e.target.checked)}
                  className="rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                />
                <span className="text-sm text-gray-700">Push to RP</span>
              </label>
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading || !launchId || !component}
              className="btn bg-purple-600 text-white hover:bg-purple-700 focus:ring-purple-500"
            >
              <Send className="h-4 w-4 mr-2" />
              Investigate
            </button>
            
            {data && (
              <button
                type="button"
                onClick={handleReset}
                className="btn btn-outline"
              >
                <RotateCcw className="h-4 w-4 mr-2" />
                New Investigation
              </button>
            )}
          </div>
        </form>
      </div>

      {loading && <LoadingOverlay message="Investigating failures (this may take a while)..." />}

      {error && (
        <div className="card p-4 border-red-200 bg-red-50">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {data && (
        <div className="space-y-6">
          <div className="card p-6 border-purple-200">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Investigation Results</h2>
                <p className="text-sm text-gray-500">
                  Launch {data.launch_id} / {data.component}
                </p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-gray-900">{data.total_failures}</div>
                <div className="text-sm text-gray-500">failures investigated</div>
              </div>
            </div>
            
            <SummaryChart summary={data.summary} total={data.total_failures} />
          </div>

          <div className="space-y-3">
            {data.results.map((result, index) => (
              <ResultCard key={result.test_id} result={result} index={index} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
