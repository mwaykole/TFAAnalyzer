import { cn } from '../utils/cn'
import { Bug, Wrench, Zap, Server, Settings, Link, Database, HelpCircle } from 'lucide-react'

interface CategoryBadgeProps {
  category: string
  confidence?: number
  className?: string
}

const categoryConfig: Record<string, { color: string; icon: typeof Bug; label: string }> = {
  'Product Bug': { color: 'bg-red-100 text-red-800', icon: Bug, label: 'Product Bug' },
  'PRODUCT_BUG': { color: 'bg-red-100 text-red-800', icon: Bug, label: 'Product Bug' },
  'Test Automation Issue': { color: 'bg-yellow-100 text-yellow-800', icon: Wrench, label: 'Automation Issue' },
  'AUTOMATION_BUG': { color: 'bg-yellow-100 text-yellow-800', icon: Wrench, label: 'Automation Bug' },
  'Flaky Test': { color: 'bg-blue-100 text-blue-800', icon: Zap, label: 'Flaky Test' },
  'FLAKY_TEST': { color: 'bg-blue-100 text-blue-800', icon: Zap, label: 'Flaky Test' },
  'Infrastructure Issue': { color: 'bg-purple-100 text-purple-800', icon: Server, label: 'Infrastructure' },
  'INFRASTRUCTURE': { color: 'bg-purple-100 text-purple-800', icon: Server, label: 'Infrastructure' },
  'CONFIGURATION': { color: 'bg-orange-100 text-orange-800', icon: Settings, label: 'Configuration' },
  'EXTERNAL_DEPENDENCY': { color: 'bg-cyan-100 text-cyan-800', icon: Link, label: 'External Dep' },
  'DATA_ISSUE': { color: 'bg-pink-100 text-pink-800', icon: Database, label: 'Data Issue' },
  'UNKNOWN': { color: 'bg-gray-100 text-gray-800', icon: HelpCircle, label: 'Unknown' },
}

export function CategoryBadge({ category, confidence, className }: CategoryBadgeProps) {
  const config = categoryConfig[category] || { 
    color: 'bg-gray-100 text-gray-800', 
    icon: HelpCircle, 
    label: category 
  }
  const Icon = config.icon

  return (
    <span className={cn(
      'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm font-medium',
      config.color,
      className
    )}>
      <Icon className="h-4 w-4" />
      {config.label}
      {confidence !== undefined && (
        <span className="ml-1 text-xs opacity-75">({Math.round(confidence * 100)}%)</span>
      )}
    </span>
  )
}
