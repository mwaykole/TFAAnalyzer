import { useState, useEffect, useRef } from 'react'
import { Terminal, X, Maximize2, Minimize2, Trash2 } from 'lucide-react'
import { cn } from '../utils/cn'

interface LogEntry {
  timestamp: string
  level: string
  message?: string
  event?: string
  [key: string]: unknown
}

interface LogsPanelProps {
  className?: string
}

export function LogsPanel({ className }: LogsPanelProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!isOpen) return

    const apiUrl = import.meta.env.VITE_API_URL || ''
    const eventSource = new EventSource(`${apiUrl}/api/v1/logs/stream`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setIsConnected(true)
    }

    eventSource.onmessage = (event) => {
      try {
        const entry = JSON.parse(event.data)
        setLogs(prev => [...prev.slice(-200), entry])
      } catch (e) {
        console.error('Failed to parse log entry:', e)
      }
    }

    eventSource.onerror = () => {
      setIsConnected(false)
    }

    return () => {
      eventSource.close()
      eventSourceRef.current = null
    }
  }, [isOpen])

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs])

  const clearLogs = () => setLogs([])

  const getLevelColor = (level: string) => {
    switch (level?.toUpperCase()) {
      case 'ERROR': return 'text-red-400'
      case 'WARNING': return 'text-yellow-400'
      case 'INFO': return 'text-blue-400'
      case 'DEBUG': return 'text-gray-400'
      default: return 'text-gray-300'
    }
  }

  const formatEntry = (entry: LogEntry) => {
    const time = entry.timestamp?.split('T')[1]?.split('.')[0] || ''
    
    // Extract the event/message
    const event = entry.event || entry.message || ''
    
    // Get all other fields as details (exclude common metadata fields)
    const excludeKeys = ['timestamp', 'level', 'event', 'message', 'logger']
    const details = Object.entries(entry)
      .filter(([key]) => !excludeKeys.includes(key))
      .map(([key, value]) => {
        // Truncate long values
        const strValue = typeof value === 'string' 
          ? (value.length > 50 ? value.slice(0, 50) + '...' : value)
          : JSON.stringify(value)
        return `${key}=${strValue}`
      })
      .join(' ')
    
    const msg = details ? `${event} ${details}` : event
    return { time, msg }
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className={cn(
          'fixed bottom-4 right-4 p-3 rounded-full bg-gray-800 text-white shadow-lg hover:bg-gray-700 transition-colors z-50',
          className
        )}
        title="Open Logs"
      >
        <Terminal className="h-5 w-5" />
      </button>
    )
  }

  return (
    <div
      className={cn(
        'fixed bg-gray-900 text-gray-100 shadow-2xl z-50 flex flex-col',
        isExpanded 
          ? 'inset-4 rounded-xl' 
          : 'bottom-4 right-4 w-[800px] h-[500px] rounded-lg',
        className
      )}
    >
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-green-400" />
          <span className="font-medium text-sm">Server Logs</span>
          <span className={cn(
            'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs',
            isConnected ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
          )}>
            <span className={cn(
              'h-1.5 w-1.5 rounded-full',
              isConnected ? 'bg-green-400' : 'bg-red-400'
            )} />
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={clearLogs}
            className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white"
            title="Clear logs"
          >
            <Trash2 className="h-4 w-4" />
          </button>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white"
            title={isExpanded ? 'Minimize' : 'Maximize'}
          >
            {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto font-mono text-xs p-2 space-y-0.5">
        {logs.length === 0 ? (
          <div className="text-gray-500 text-center py-8">
            Waiting for logs...
          </div>
        ) : (
          logs.map((entry, i) => {
            const { time } = formatEntry(entry)
            const event = entry.event || entry.message || ''
            
            // Get details separately for better formatting
            const excludeKeys = ['timestamp', 'level', 'event', 'message', 'logger']
            const detailParts = Object.entries(entry)
              .filter(([key]) => !excludeKeys.includes(key))
              .map(([key, value]) => {
                const strValue = typeof value === 'string' 
                  ? (value.length > 60 ? value.slice(0, 60) + '...' : value)
                  : JSON.stringify(value)
                return { key, value: strValue }
              })
            
            return (
              <div key={i} className="flex gap-2 hover:bg-gray-800 px-1 py-0.5 rounded group">
                <span className="text-gray-500 shrink-0 text-xs">{time}</span>
                <span className={cn('shrink-0 w-12 text-xs', getLevelColor(entry.level))}>
                  [{entry.level?.slice(0, 4) || 'LOG'}]
                </span>
                <span className="text-gray-100 font-medium">{event}</span>
                {detailParts.length > 0 && (
                  <span className="text-gray-400 text-xs">
                    {detailParts.map((d, idx) => (
                      <span key={idx} className="ml-2">
                        <span className="text-gray-500">{d.key}=</span>
                        <span className="text-cyan-400">{d.value}</span>
                      </span>
                    ))}
                  </span>
                )}
              </div>
            )
          })
        )}
        <div ref={logsEndRef} />
      </div>

      <div className="px-4 py-1.5 border-t border-gray-700 text-xs text-gray-500">
        {logs.length} entries
      </div>
    </div>
  )
}
