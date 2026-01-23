import { ChevronDown, ChevronUp, CheckCircle, Database, PlayCircle, XCircle, AlertTriangle, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { CategoryBadge } from './CategoryBadge'
import { SeverityBadge } from './StatusBadge'
import type { AnalysisResult, InvestigationResult } from '../types'

interface ResultCardProps {
  result: AnalysisResult | InvestigationResult
  index: number
}

function VerificationBadge({ status }: { status: string }) {
  const config: Record<string, { icon: typeof CheckCircle; color: string; label: string }> = {
    passed: { icon: CheckCircle, color: 'text-green-600 bg-green-50', label: 'Re-run PASSED' },
    failed: { icon: XCircle, color: 'text-red-600 bg-red-50', label: 'Re-run FAILED' },
    flaky: { icon: RotateCcw, color: 'text-yellow-600 bg-yellow-50', label: 'FLAKY' },
    timeout: { icon: AlertTriangle, color: 'text-orange-600 bg-orange-50', label: 'TIMEOUT' },
    consistent_fail: { icon: XCircle, color: 'text-red-600 bg-red-50', label: 'Consistent Failure' },
    inconclusive: { icon: AlertTriangle, color: 'text-gray-600 bg-gray-50', label: 'Inconclusive' },
  }
  
  const { icon: Icon, color, label } = config[status] || { icon: PlayCircle, color: 'text-gray-500 bg-gray-50', label: status }
  
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      <Icon className="h-3 w-3" />
      {label}
    </span>
  )
}

export function ResultCard({ result, index }: ResultCardProps) {
  const [expanded, setExpanded] = useState(false)

  const isInvestigation = 'evidence_summary' in result
  const investigationResult = isInvestigation ? result as InvestigationResult : null

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm text-gray-500">#{index + 1}</span>
              <h3 className="font-medium text-gray-900 truncate" title={result.test_name}>
                {result.test_name}
              </h3>
              {'cached' in result && result.cached && (
                <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                  <Database className="h-3 w-3" />
                  cached
                </span>
              )}
              {'from_rp' in result && result.from_rp && (
                <span className="inline-flex items-center gap-1 text-xs text-green-600">
                  <CheckCircle className="h-3 w-3" />
                  from RP
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <CategoryBadge 
                category={result.classification.category} 
                confidence={result.classification.confidence}
              />
              <SeverityBadge severity={result.classification.severity} />
              {investigationResult?.verified && investigationResult.verification_result !== 'not_run' && (
                <VerificationBadge status={investigationResult.verification_result} />
              )}
            </div>
          </div>
          <div className="flex-shrink-0">
            {expanded ? (
              <ChevronUp className="h-5 w-5 text-gray-400" />
            ) : (
              <ChevronDown className="h-5 w-5 text-gray-400" />
            )}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 p-4 bg-gray-50 space-y-4">
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-1">Root Cause</h4>
            <p className="text-sm text-gray-600">{result.root_cause}</p>
          </div>
          
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-1">Reasoning</h4>
            <p className="text-sm text-gray-600">{result.reasoning}</p>
          </div>

          {isInvestigation && (
            <div>
              <h4 className="text-sm font-medium text-gray-700 mb-1">Evidence</h4>
              <p className="text-sm text-gray-600">{investigationResult?.evidence_summary}</p>
              
              {/* Verification Result */}
              {investigationResult?.verified && investigationResult.verification_result !== 'not_run' && (
                <div className="mt-3 p-3 rounded-lg bg-white border border-gray-200">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm font-medium text-gray-700">Verification:</span>
                    <VerificationBadge status={investigationResult.verification_result} />
                  </div>
                  
                  {investigationResult.verification_details && (
                    <div className="space-y-2 text-sm">
                      {investigationResult.verification_details.reason && (
                        <p className="text-gray-600">
                          <span className="font-medium">Analysis:</span> {investigationResult.verification_details.reason}
                        </p>
                      )}
                      
                      {investigationResult.verification_details.confidence > 0 && (
                        <p className="text-gray-500">
                          <span className="font-medium">Confidence:</span> {Math.round(investigationResult.verification_details.confidence * 100)}%
                        </p>
                      )}
                      
                      {investigationResult.verification_details.details?.history && (
                        <div className="text-gray-500 text-xs">
                          <span className="font-medium">History:</span>{' '}
                          {investigationResult.verification_details.details.history.total_runs} runs, 
                          {' '}{investigationResult.verification_details.details.history.pass_rate} pass rate
                          {investigationResult.verification_details.details.history.is_flaky && ' (flaky)'}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {result.recommendation && (
            <div>
              <h4 className="text-sm font-medium text-gray-700 mb-1">Recommendation</h4>
              <p className="text-sm text-gray-600">{result.recommendation}</p>
            </div>
          )}

          <div className="flex items-center gap-4 pt-2">
            <span className="text-xs text-gray-500">
              Test ID: {result.test_id}
            </span>
            <span className="text-xs text-gray-500">
              Confidence: {result.classification.confidence_percent}%
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
