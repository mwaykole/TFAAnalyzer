import { useState, useMemo } from 'react'
import { Search, Microscope, Send, RotateCcw, ChevronDown, Info, Zap, Clock, PlayCircle, History, FileSearch, Link } from 'lucide-react'
import { useAnalyze } from '../hooks/useAnalyze'
import { useInvestigate } from '../hooks/useInvestigate'
import { useHealth } from '../hooks/useHealth'
import { ResultCard } from '../components/ResultCard'
import { SummaryChart } from '../components/SummaryChart'
import { LoadingOverlay } from '../components/LoadingSpinner'
import { cn } from '../utils/cn'
import { extractLaunchId, isRPUrl, parseRPUrl } from '../utils/urlParser'

type AnalysisMode = 'quick' | 'deep'

interface VerificationOption {
  id: string
  label: string
  description: string
  detail: string
  icon: typeof PlayCircle
}

const verificationOptions: VerificationOption[] = [
  {
    id: 'run_test',
    label: 'Re-run Test',
    description: 'Execute with pytest',
    detail: 'Actually re-runs the failed test using "uv run pytest". Verifies if the failure is reproducible or was a one-time flake.',
    icon: PlayCircle,
  },
  {
    id: 'analyze_history',
    label: 'Analyze History',
    description: 'Check patterns & code',
    detail: 'Analyzes pass/fail patterns from ReportPortal history and examines test code for flakiness indicators (sleep calls, timeouts, retry decorators).',
    icon: History,
  },
]

export function Analyze() {
  const { health } = useHealth()
  const analyzeHook = useAnalyze()
  const investigateHook = useInvestigate()
  
  const [launchId, setLaunchId] = useState('')
  const [component, setComponent] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('quick')
  const [pushToRp, setPushToRp] = useState(false)
  const [useCache, setUseCache] = useState(true)
  const [useLlm, setUseLlm] = useState(true)
  const [provider, setProvider] = useState('anthropic')
  
  // Verification checkboxes (can select multiple)
  const [runTest, setRunTest] = useState(false)
  const [analyzeHistory, setAnalyzeHistory] = useState(false)

  const isDeep = analysisMode === 'deep'
  const { data, loading, error } = isDeep ? investigateHook : analyzeHook
  const activeHook = isDeep ? investigateHook : analyzeHook
  
  // Count selected verifications for display
  const selectedVerifications = [runTest, analyzeHistory].filter(Boolean).length

  // Parse URL input to extract launch ID
  const parsedUrl = useMemo(() => {
    if (!launchId) return null
    if (isRPUrl(launchId)) {
      return parseRPUrl(launchId)
    }
    return null
  }, [launchId])
  
  // The actual launch ID to use (extracted from URL or as-is)
  const effectiveLaunchId = useMemo(() => {
    return extractLaunchId(launchId)
  }, [launchId])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!effectiveLaunchId || !component) return

    // Send the original launchId - backend will extract ID from URL if needed
    if (isDeep) {
      await investigateHook.investigate({
        launch_id: launchId, // Backend handles URL parsing
        component,
        push_to_rp: pushToRp,
        run_test: runTest,
        analyze_history: analyzeHistory,
        provider,
      })
    } else {
      await analyzeHook.analyze({
        launch_id: launchId, // Backend handles URL parsing
        component,
        push_to_rp: pushToRp,
        use_cache: useCache,
        use_llm: useLlm,
        provider,
      })
    }
  }

  const handleReset = () => {
    activeHook.reset()
    setLaunchId('')
    setComponent('')
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Search className="h-7 w-7 text-primary-600" />
          Failure Analysis
        </h1>
        <p className="mt-1 text-gray-600">
          Analyze test failures using AI-powered classification and root cause analysis
        </p>
      </div>

      {/* Analysis Mode Toggle */}
      <div className="card p-4">
        <label className="text-sm font-medium text-gray-700 mb-3 block">Analysis Mode</label>
        <div className="grid grid-cols-2 gap-4">
          <button
            type="button"
            onClick={() => setAnalysisMode('quick')}
            className={cn(
              'flex items-start gap-3 p-4 rounded-lg border-2 transition-all text-left',
              analysisMode === 'quick'
                ? 'border-primary-500 bg-primary-50'
                : 'border-gray-200 hover:border-gray-300'
            )}
          >
            <Zap className={cn('h-5 w-5 mt-0.5', analysisMode === 'quick' ? 'text-primary-600' : 'text-gray-400')} />
            <div>
              <div className={cn('font-medium', analysisMode === 'quick' ? 'text-primary-900' : 'text-gray-900')}>
                Quick Analysis
              </div>
              <div className="text-sm text-gray-500 mt-1">
                Fast classification using YAML rules + single LLM call. Best for triaging many failures quickly.
              </div>
            </div>
          </button>
          
          <button
            type="button"
            onClick={() => setAnalysisMode('deep')}
            className={cn(
              'flex items-start gap-3 p-4 rounded-lg border-2 transition-all text-left',
              analysisMode === 'deep'
                ? 'border-purple-500 bg-purple-50'
                : 'border-gray-200 hover:border-gray-300'
            )}
          >
            <Microscope className={cn('h-5 w-5 mt-0.5', analysisMode === 'deep' ? 'text-purple-600' : 'text-gray-400')} />
            <div>
              <div className={cn('font-medium', analysisMode === 'deep' ? 'text-purple-900' : 'text-gray-900')}>
                Deep Investigation
              </div>
              <div className="text-sm text-gray-500 mt-1">
                Thorough RCA using Thinker-Critic-Refiner pattern (3 LLM calls). Includes verification options.
              </div>
            </div>
          </button>
        </div>
      </div>

      {/* Deep mode warning */}
      {isDeep && (
        <div className="flex items-start gap-3 p-4 rounded-lg bg-purple-50 border border-purple-200">
          <Clock className="h-5 w-5 text-purple-600 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-purple-900">Deep investigation takes longer</p>
            <p className="text-purple-700">
              Uses 3 LLM calls per failure (Thinker, Critic, Refiner) for more accurate root cause analysis.
              Consider Quick Analysis for initial triage.
            </p>
          </div>
        </div>
      )}

      {/* Main Form */}
      <div className="card">
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label htmlFor="launchId" className="label">Launch ID or URL</label>
              <div className="relative">
                <input
                  type="text"
                  id="launchId"
                  value={launchId}
                  onChange={(e) => setLaunchId(e.target.value)}
                  placeholder="9657 or paste full ReportPortal URL"
                  className={cn(
                    "input pr-10",
                    parsedUrl && "border-green-400 focus:border-green-500 focus:ring-green-500"
                  )}
                  required
                />
                {parsedUrl && (
                  <div className="absolute inset-y-0 right-0 flex items-center pr-3">
                    <Link className="h-4 w-4 text-green-500" />
                  </div>
                )}
              </div>
              {parsedUrl ? (
                <p className="mt-1 text-xs text-green-600 flex items-center gap-1">
                  <span className="inline-block w-2 h-2 bg-green-500 rounded-full"></span>
                  URL detected! Using launch ID: <span className="font-mono font-medium">{effectiveLaunchId}</span>
                  {parsedUrl.project && <span className="text-gray-500 ml-1">(project: {parsedUrl.project})</span>}
                </p>
              ) : (
                <p className="mt-1 text-xs text-gray-500">
                  Paste the full URL from ReportPortal - we'll extract the launch ID automatically
                </p>
              )}
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
            <div className="space-y-4 p-4 rounded-lg bg-gray-50">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
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

                {!isDeep && (
                  <>
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
                  </>
                )}
                
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

              {/* Verification Options (Deep mode only) - Checkboxes */}
              {isDeep && (
                <div className="pt-4 border-t border-gray-200">
                  <div className="flex items-center justify-between mb-3">
                    <label className="text-sm font-medium text-gray-700 flex items-center gap-2">
                      <FileSearch className="h-4 w-4" />
                      Verification Options
                      {selectedVerifications > 0 && (
                        <span className="ml-2 px-2 py-0.5 text-xs bg-purple-100 text-purple-700 rounded-full">
                          {selectedVerifications} selected
                        </span>
                      )}
                    </label>
                    <span className="text-xs text-gray-500">Select any combination</span>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {verificationOptions.map((option) => {
                      const Icon = option.icon
                      const isChecked = option.id === 'run_test' ? runTest : analyzeHistory
                      const setChecked = option.id === 'run_test' ? setRunTest : setAnalyzeHistory
                      
                      return (
                        <label
                          key={option.id}
                          className={cn(
                            'flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all',
                            isChecked
                              ? 'border-purple-400 bg-purple-50'
                              : 'border-gray-200 hover:border-gray-300 bg-white'
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => setChecked(e.target.checked)}
                            className="mt-1 rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                          />
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <Icon className={cn('h-4 w-4', isChecked ? 'text-purple-600' : 'text-gray-400')} />
                              <span className={cn('font-medium', isChecked ? 'text-purple-900' : 'text-gray-900')}>
                                {option.label}
                              </span>
                              <span className="text-xs text-gray-500">- {option.description}</span>
                            </div>
                            <p className="text-sm text-gray-600 mt-1">{option.detail}</p>
                          </div>
                        </label>
                      )
                    })}
                  </div>
                  
                  {selectedVerifications === 0 && (
                    <p className="mt-2 text-xs text-gray-500 flex items-center gap-1">
                      <Info className="h-3 w-3" />
                      No verification selected - only LLM-based RCA will be performed
                    </p>
                  )}
                  {selectedVerifications === 2 && (
                    <p className="mt-2 text-xs text-purple-600 flex items-center gap-1">
                      <Info className="h-3 w-3" />
                      Both verifications selected - will run in parallel for comprehensive analysis
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading || !launchId || !component}
              className={cn(
                'btn text-white',
                isDeep 
                  ? 'bg-purple-600 hover:bg-purple-700 focus:ring-purple-500'
                  : 'btn-primary'
              )}
            >
              <Send className="h-4 w-4 mr-2" />
              {isDeep ? 'Investigate' : 'Analyze'}
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

      {loading && (
        <LoadingOverlay 
          message={isDeep ? "Investigating failures (this may take a while)..." : "Analyzing failures..."} 
        />
      )}

      {error && (
        <div className="card p-4 border-red-200 bg-red-50">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {data && (
        <div className="space-y-6">
          <div className={cn('card p-6', isDeep && 'border-purple-200')}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  {isDeep ? 'Investigation' : 'Analysis'} Results
                </h2>
                <p className="text-sm text-gray-500">
                  Launch {data.launch_id} / {data.component}
                </p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-gray-900">{data.total_failures}</div>
                <div className="text-sm text-gray-500">
                  {isDeep ? 'failures investigated' : 'total failures'}
                </div>
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
