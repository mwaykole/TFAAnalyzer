import { cn } from '../utils/cn'
import type { HealthStatus, Severity } from '../types'

interface StatusBadgeProps {
  status: HealthStatus
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const styles = {
    healthy: 'bg-green-100 text-green-800',
    degraded: 'bg-yellow-100 text-yellow-800',
    unhealthy: 'bg-red-100 text-red-800',
  }

  return (
    <span className={cn(
      'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
      styles[status],
      className
    )}>
      {status}
    </span>
  )
}

interface SeverityBadgeProps {
  severity: Severity
  className?: string
}

export function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  const styles = {
    LOW: 'bg-gray-100 text-gray-800',
    MEDIUM: 'bg-yellow-100 text-yellow-800',
    HIGH: 'bg-orange-100 text-orange-800',
    CRITICAL: 'bg-red-100 text-red-800',
  }

  const icons = {
    LOW: '○',
    MEDIUM: '◐',
    HIGH: '●',
    CRITICAL: '⬤',
  }

  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium',
      styles[severity],
      className
    )}>
      <span>{icons[severity]}</span>
      {severity}
    </span>
  )
}
