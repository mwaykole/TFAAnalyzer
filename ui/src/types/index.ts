export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy'

export interface ClassificationDetails {
  category: string
  confidence: number
  confidence_percent: number
  severity: Severity
}

export interface AnalysisResult {
  test_name: string
  test_id: string
  classification: ClassificationDetails
  root_cause: string
  reasoning: string
  recommendation: string
  cached: boolean
  from_rp: boolean
}

export interface AnalyzeResponse {
  launch_id: string
  component: string
  total_failures: number
  results: AnalysisResult[]
  summary: Record<string, number>
}

export interface VerificationDetails {
  mode: 'none' | 'run' | 'analyze-history'
  status: string
  output: string
  confidence: number
  reason: string
  is_intermittent: boolean
  details: {
    history?: {
      total_runs: number
      passed: number
      failed: number
      pass_rate: string
      pattern: string
      is_flaky: boolean
      last_status: string
    }
    code?: {
      has_flaky_marker: boolean
      has_timing_issues: boolean
      timing_issues: string[]
    }
  }
}

export interface InvestigationResult {
  test_name: string
  test_id: string
  classification: ClassificationDetails
  root_cause: string
  reasoning: string
  evidence_summary: string
  recommendation: string
  verified: boolean
  verification_result: string
  verification_details?: VerificationDetails
}

export interface InvestigateResponse {
  launch_id: string
  component: string
  total_failures: number
  results: InvestigationResult[]
  summary: Record<string, number>
}

export interface HealthResponse {
  status: HealthStatus
  version: string
  cache_available: boolean
  rp_configured: boolean
  llm_providers: string[]
}

export interface AnalyzeRequest {
  launch_id: string
  component: string
  test_id?: string
  push_to_rp: boolean
  use_cache: boolean
  use_llm: boolean
  provider: string
}

export type VerifyMode = 'none' | 'run' | 'analyze-history'

export interface InvestigateRequest {
  launch_id: string
  component: string
  test_id?: string
  push_to_rp: boolean
  verify_mode: VerifyMode
  verify_tests?: boolean  // Legacy support
  provider: string
}
