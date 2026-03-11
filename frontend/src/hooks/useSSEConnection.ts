import { useEffect, useRef } from "react"
import { createSSEConnection } from "@/lib/api"
import type { SSECallbacks } from "@/lib/api/sse"

/**
 * Hook to manage SSE connection lifecycle
 * @param threadId - Thread ID to connect to
 * @param callbacks - SSE event callbacks
 * @param enabled - Whether the connection should be active (default: true)
 */
export function useSSEConnection(
  threadId: string | null,
  callbacks: SSECallbacks,
  enabled: boolean = true
) {
  const cleanupRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    // Don't connect if disabled or no threadId
    if (!enabled || !threadId) {
      return
    }

    // Create SSE connection
    cleanupRef.current = createSSEConnection(threadId, callbacks)

    // Cleanup on unmount or when dependencies change
    return () => {
      if (cleanupRef.current) {
        cleanupRef.current()
        cleanupRef.current = null
      }
    }
  }, [threadId, enabled, callbacks])

  return {
    disconnect: () => {
      if (cleanupRef.current) {
        cleanupRef.current()
        cleanupRef.current = null
      }
    },
  }
}
