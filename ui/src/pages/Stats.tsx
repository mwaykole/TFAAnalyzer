import { BarChart3, AlertCircle } from 'lucide-react'

export function Stats() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <BarChart3 className="h-7 w-7 text-green-600" />
          Statistics & Trends
        </h1>
        <p className="mt-1 text-gray-600">
          View classification trends and component health metrics
        </p>
      </div>

      <div className="card p-8 text-center">
        <AlertCircle className="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Statistics Dashboard Coming Soon
        </h2>
        <p className="text-gray-600 max-w-md mx-auto">
          This page will display historical classification trends, component health metrics, 
          and accuracy reports. For now, use the CLI command:
        </p>
        <code className="mt-4 inline-block px-4 py-2 bg-gray-100 rounded-lg text-sm">
          python main.py stats --days 30
        </code>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card p-6">
          <div className="text-sm font-medium text-gray-500 mb-1">CLI Commands</div>
          <div className="space-y-2 text-sm text-gray-700">
            <div><code className="bg-gray-100 px-1 rounded">stats</code> - Overall statistics</div>
            <div><code className="bg-gray-100 px-1 rounded">health</code> - Component health</div>
            <div><code className="bg-gray-100 px-1 rounded">trends</code> - Failure trends</div>
            <div><code className="bg-gray-100 px-1 rounded">dashboard</code> - Full analytics</div>
          </div>
        </div>

        <div className="card p-6">
          <div className="text-sm font-medium text-gray-500 mb-1">Accuracy Tracking</div>
          <div className="space-y-2 text-sm text-gray-700">
            <div><code className="bg-gray-100 px-1 rounded">accuracy-report</code></div>
            <div><code className="bg-gray-100 px-1 rounded">record-feedback</code></div>
            <div><code className="bg-gray-100 px-1 rounded">validate-analysis</code></div>
          </div>
        </div>

        <div className="card p-6">
          <div className="text-sm font-medium text-gray-500 mb-1">Reports</div>
          <div className="space-y-2 text-sm text-gray-700">
            <div><code className="bg-gray-100 px-1 rounded">digest --days 7</code></div>
            <div>Weekly summary report</div>
          </div>
        </div>
      </div>
    </div>
  )
}
