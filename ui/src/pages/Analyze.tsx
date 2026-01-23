import { useState } from 'react'
import { Search, Send, RotateCcw, ChevronDown } from 'lucide-react'
import { useAnalyze } from '../hooks/useAnalyze'
import { useHealth } from '../hooks/useHealth'
import { ResultCard } from '../components/ResultCard'
import { SummaryChart } from '../components/SummaryChart'
import { LoadingOverlay } from '../components/LoadingSpinner'
import { cn } from '../utils/cn'

export function Analyze() {
  const { data, loading, error, analyze, reset } = useAnalyze()
  const { health } = useHealth()
  
  const [launchId, setLaunchId] = useState('')
  const [component, setComponent] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [pushToRp, setPushToRp] = useState(false)
  const [useCache, setUseCache] = useState(true)
  const [useLlm, setUseLlm] = useState(true)
  const [provider, setProvider] = useState('anthropic')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!launchId || !component) return

    await analyze({
      launch_id: launchId,
      component,
      push_to_rp: pushToRp,
      use_cache: useCache,
      use_llm: useLlm,
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
          <Search className="h-7 w-7 text-primary-600" />
          Quick Analysis
        </h1>
        <p className="mt-1 text-gray-600">
          Analyze test failures using AI-powered classification
        </p>
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
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 p-4 rounded-lg bg-gray-50">
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
              
              <label className="flex items-center gap-2 p-2">
                <input
                  type="checkbox"
                  checked={useCache}
                  onChange={(e) => setUseCache(e.target.checked)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Use Cache</span>
              </label>
              
              <label className="flex items-center gap-2 p-2">
                <input
                  type="checkbox"
                  checked={useLlm}
                  onChange={(e) => setUseLlm(e.target.checked)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Use LLM</span>
              </label>
              
              <label className="flex items-center gap-2 p-2">
                <input
                  type="checkbox"
                  checked={pushToRp}
                  onChange={(e) => setPushToRp(e.target.checked)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Push to RP</span>
              </label>
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading || !launchId || !component}
              className="btn btn-primary"
            >
              <Send className="h-4 w-4 mr-2" />
              Analyze
            </button>
            
            {data && (
              <button
                type="button"
                onClick={handleReset}
                className="btn btn-outline"
              >
                <RotateCcw className="h-4 w-4 mr-2" />
                New Analysis
              </button>
            )}
          </div>
        </form>
      </div>

      {loading && <LoadingOverlay message="Analyzing failures..." />}

      {error && (
        <div className="card p-4 border-red-200 bg-red-50">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {data && (
        <div className="space-y-6">
          <div className="card p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Analysis Results</h2>
                <p className="text-sm text-gray-500">
                  Launch {data.launch_id} / {data.component}
                </p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-gray-900">{data.total_failures}</div>
                <div className="text-sm text-gray-500">total failures</div>
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
