import { Link } from 'react-router-dom'
import { 
  Search, 
  BarChart3, 
  Zap,
  Server,
  Database
} from 'lucide-react'
import { useHealth } from '../hooks/useHealth'
import { StatusBadge } from '../components/StatusBadge'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function Dashboard() {
  const { health, loading, error } = useHealth()

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Test Failure Analyzer</h1>
        <p className="mt-2 text-gray-600">
          AI-powered analysis of test failures in ReportPortal
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Link
          to="/analyze"
          className="card p-6 hover:border-primary-300 hover:shadow-md transition-all group"
        >
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-xl bg-primary-100 text-primary-600 flex items-center justify-center group-hover:bg-primary-200 transition-colors">
              <Search className="h-6 w-6" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">Analyze Failures</h3>
              <p className="text-sm text-gray-500">
                Quick or deep analysis with AI-powered classification
              </p>
            </div>
          </div>
        </Link>

        <Link
          to="/stats"
          className="card p-6 hover:border-green-300 hover:shadow-md transition-all group"
        >
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-xl bg-green-100 text-green-600 flex items-center justify-center group-hover:bg-green-200 transition-colors">
              <BarChart3 className="h-6 w-6" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">Statistics</h3>
              <p className="text-sm text-gray-500">View trends and metrics</p>
            </div>
          </div>
        </Link>
      </div>

      <div className="card">
        <div className="p-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">System Status</h2>
        </div>
        <div className="p-4">
          {loading ? (
            <LoadingSpinner size="sm" />
          ) : error ? (
            <div className="text-red-600 text-sm">{error}</div>
          ) : health ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-gray-600">API Status</span>
                <StatusBadge status={health.status} />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50">
                  <Database className={`h-5 w-5 ${health.cache_available ? 'text-green-500' : 'text-gray-400'}`} />
                  <div>
                    <div className="text-sm font-medium text-gray-900">Cache</div>
                    <div className="text-xs text-gray-500">
                      {health.cache_available ? 'Available' : 'Unavailable'}
                    </div>
                  </div>
                </div>
                
                <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50">
                  <Server className={`h-5 w-5 ${health.rp_configured ? 'text-green-500' : 'text-gray-400'}`} />
                  <div>
                    <div className="text-sm font-medium text-gray-900">ReportPortal</div>
                    <div className="text-xs text-gray-500">
                      {health.rp_configured ? 'Configured' : 'Not Configured'}
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <div className="text-sm font-medium text-gray-700 mb-2">LLM Providers</div>
                <div className="flex flex-wrap gap-2">
                  {health.llm_providers.map((provider) => (
                    <span
                      key={provider}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-gray-100 text-gray-700 text-xs"
                    >
                      <Zap className="h-3 w-3" />
                      {provider}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="card p-6">
        <h2 className="font-semibold text-gray-900 mb-4">Quick Start</h2>
        <div className="prose prose-sm text-gray-600">
          <ol className="space-y-2">
            <li>Start the TFA API server: <code className="bg-gray-100 px-1 rounded">python main.py serve</code></li>
            <li>Go to <Link to="/analyze" className="text-primary-600 hover:underline">Analyze</Link> page</li>
            <li>Enter your launch ID and component name</li>
            <li>Click "Analyze" to get AI-powered failure classifications</li>
          </ol>
        </div>
      </div>
    </div>
  )
}
