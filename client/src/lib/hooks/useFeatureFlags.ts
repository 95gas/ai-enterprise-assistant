/**
 * Phase 50.A — feature-flag hook for the chat client.
 *
 * Fetches once on mount + caches the snapshot. The backend's
 * `GET /api/general/v0/system/feature-flags` returns the flags
 * scoped to the calling user (e.g. `admin_agent_enabled` is
 * already conjoined with the caller's admin-group membership
 * server-side, so the client can render directly off the value
 * without re-checking `user.groups`).
 *
 * Returns `{ flags, loading }`. While `loading` is true we treat
 * every flag as `false` (fail-closed — never render an admin-only
 * surface that hasn't been server-confirmed yet).
 */

import { useEffect, useState } from "react"

import { FeatureFlags, getFeatureFlags } from "@/api/featureFlags"

const DEFAULT: FeatureFlags = {
  admin_agent_enabled: false,
}

let cached: FeatureFlags | null = null

export default function useFeatureFlags(): { flags: FeatureFlags; loading: boolean } {
  const [flags, setFlags] = useState<FeatureFlags>(cached ?? DEFAULT)
  const [loading, setLoading] = useState<boolean>(cached === null)

  useEffect(() => {
    if (cached !== null) return
    let alive = true
    getFeatureFlags()
      .then((next) => {
        cached = next
        if (alive) {
          setFlags(next)
          setLoading(false)
        }
      })
      .catch(() => {
        if (alive) {
          setLoading(false) // Stay on DEFAULT (all off) — fail-closed.
        }
      })
    return () => {
      alive = false
    }
  }, [])

  return { flags, loading }
}
