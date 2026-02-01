/**
 * URL parser utilities for extracting IDs from ReportPortal URLs.
 * 
 * Makes it easier for users to just paste the full URL instead of
 * manually extracting the launch ID.
 * 
 * Supported URL formats:
 * - https://reportportal.example.com/ui/#project/launches/all/9378
 * - https://rp.example.com/ui/#project-name/launches/all/9378
 * - https://rp.example.com/ui/#project/userdebug/all/9378/test-item/510078
 * - https://rp.example.com/ui/#project/launches/829/9355 (direct launch ID without 'all')
 * - Just the ID: 9378
 */

export interface ParsedRPUrl {
  launchId: string
  testItemId?: string
  project?: string
  baseUrl?: string
}

/**
 * Extract launch ID from URL or return as-is if already an ID.
 */
export function extractLaunchId(input: string): string {
  if (!input) return input
  
  const trimmed = input.trim()
  
  // If it's already just a number, return it
  if (/^\d+$/.test(trimmed)) {
    return trimmed
  }
  
  // Try to parse as URL
  const parsed = parseRPUrl(trimmed)
  if (parsed?.launchId) {
    return parsed.launchId
  }
  
  // Return original if we couldn't extract
  return trimmed
}

/**
 * Parse a ReportPortal URL into components.
 */
export function parseRPUrl(url: string): ParsedRPUrl | null {
  if (!url || typeof url !== 'string') {
    return null
  }
  
  const trimmed = url.trim()
  
  // Check if it looks like a URL
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
    if (!trimmed.includes('#') && !trimmed.includes('/')) {
      return null
    }
  }
  
  try {
    // Extract fragment (part after #)
    let fragment = ''
    if (trimmed.includes('#')) {
      fragment = trimmed.split('#')[1] || ''
    }
    
    if (!fragment) {
      return null
    }
    
    // Parse the fragment path
    // Formats:
    // - project/launches/all/LAUNCH_ID
    // - project/launches/all/LAUNCH_ID/test-item/TEST_ITEM_ID
    // - project/launches/LAUNCH_ID/TEST_ITEM_ID (direct, no 'all')
    const parts = fragment.replace(/^\/|\/$/g, '').split('/')
    
    if (parts.length < 3) {
      return null
    }
    
    const project = parts[0]
    let launchId: string | undefined
    let testItemId: string | undefined
    
    // Find launch ID - it's the numeric value after "all" or "latest"
    for (let i = 0; i < parts.length; i++) {
      if ((parts[i] === 'all' || parts[i] === 'latest') && i + 1 < parts.length) {
        const potentialId = parts[i + 1]
        if (/^\d+$/.test(potentialId)) {
          launchId = potentialId
          
          // Check for test-item ID
          if (i + 3 < parts.length && parts[i + 2] === 'test-item') {
            const potentialItemId = parts[i + 3]
            if (/^\d+$/.test(potentialItemId)) {
              testItemId = potentialItemId
            }
          }
          break
        }
      }
    }
    
    // Alternative: project/launches/LAUNCH_ID or project/launches/FILTER_ID/LAUNCH_ID
    // This handles URLs like: #opendatascience/launches/829/9355
    // Where 829 could be a filter ID and 9355 is the actual launch ID
    if (!launchId) {
      for (let i = 0; i < parts.length; i++) {
        if (parts[i] === 'launches' && i + 1 < parts.length) {
          const nextPart = parts[i + 1]
          
          // If next part is 'all' or 'latest', skip and look further
          if ((nextPart === 'all' || nextPart === 'latest') && i + 2 < parts.length) {
            if (/^\d+$/.test(parts[i + 2])) {
              launchId = parts[i + 2]
              
              // Check for test-item
              if (i + 4 < parts.length && parts[i + 3] === 'test-item') {
                if (/^\d+$/.test(parts[i + 4])) {
                  testItemId = parts[i + 4]
                }
              }
            }
            break
          }
          
          // If the next part is numeric
          if (/^\d+$/.test(nextPart)) {
            // Check if there's another numeric part after this
            // Pattern: launches/FILTER_ID/LAUNCH_ID (the LAST numeric ID is usually the launch)
            if (i + 2 < parts.length && /^\d+$/.test(parts[i + 2])) {
              // Two numbers after launches - assume FILTER_ID/LAUNCH_ID
              // The second number (9355) is the launch ID
              launchId = parts[i + 2]
              // Note: parts[i+1] is the filter ID, not test_item_id
              console.debug('URL pattern: filter/launch', { filterId: nextPart, launchId })
            } else {
              // Only one number - it's the launch ID
              launchId = nextPart
              
              // Check for test-item after
              if (i + 2 < parts.length) {
                const potentialItem = parts[i + 2]
                if (potentialItem === 'test-item' && i + 3 < parts.length) {
                  if (/^\d+$/.test(parts[i + 3])) {
                    testItemId = parts[i + 3]
                  }
                }
              }
            }
            break
          }
          break
        }
      }
    }
    
    if (!launchId) {
      return null
    }
    
    // Extract base URL
    let baseUrl: string | undefined
    try {
      const urlObj = new URL(trimmed)
      baseUrl = `${urlObj.protocol}//${urlObj.host}`
    } catch {
      // Ignore URL parse errors
    }
    
    return {
      launchId,
      testItemId,
      project,
      baseUrl,
    }
  } catch {
    return null
  }
}

/**
 * Check if input looks like a ReportPortal URL.
 */
export function isRPUrl(input: string): boolean {
  if (!input) return false
  
  const lower = input.trim().toLowerCase()
  
  if (lower.startsWith('http://') || lower.startsWith('https://')) {
    return lower.includes('reportportal') || lower.includes('/ui/#') || lower.includes('/launches/')
  }
  
  return false
}
