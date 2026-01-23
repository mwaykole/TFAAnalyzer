import { CategoryBadge } from './CategoryBadge'

interface SummaryChartProps {
  summary: Record<string, number>
  total: number
}

export function SummaryChart({ summary, total }: SummaryChartProps) {
  const categories = Object.entries(summary).sort((a, b) => b[1] - a[1])

  const colors: Record<string, string> = {
    'Product Bug': 'bg-red-500',
    'PRODUCT_BUG': 'bg-red-500',
    'Test Automation Issue': 'bg-yellow-500',
    'AUTOMATION_BUG': 'bg-yellow-500',
    'Flaky Test': 'bg-blue-500',
    'FLAKY_TEST': 'bg-blue-500',
    'Infrastructure Issue': 'bg-purple-500',
    'INFRASTRUCTURE': 'bg-purple-500',
    'CONFIGURATION': 'bg-orange-500',
    'EXTERNAL_DEPENDENCY': 'bg-cyan-500',
    'DATA_ISSUE': 'bg-pink-500',
    'UNKNOWN': 'bg-gray-500',
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 h-4 rounded-full overflow-hidden bg-gray-100">
        {categories.map(([category, count]) => (
          <div
            key={category}
            className={colors[category] || 'bg-gray-400'}
            style={{ width: `${(count / total) * 100}%` }}
            title={`${category}: ${count}`}
          />
        ))}
      </div>
      
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {categories.map(([category, count]) => (
          <div key={category} className="flex items-center justify-between gap-2 p-2 rounded-lg bg-gray-50">
            <CategoryBadge category={category} className="text-xs" />
            <span className="text-sm font-semibold text-gray-900">{count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
