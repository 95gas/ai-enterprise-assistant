/**
 * Phase 50.A — feature-flag fetcher for the chat client.
 *
 * The backend's `GET /api/general/v0/system/feature-flags` endpoint
 * returns the server-authoritative flag snapshot scoped to the
 * calling user (so the AdminAssistant flag, which conjoins
 * `ASK_ADMIN_AGENT_ENABLED=1` AND the caller's admin role, returns
 * `true` only when both conditions hold). Additive — clients
 * ignore unknown keys.
 */

export type FeatureFlags = {
  admin_agent_enabled: boolean
  // Forward-compatible: future flags get added here. The fetcher
  // tolerates partial responses (every flag defaults to `false`).
}

const DEFAULT_FLAGS: FeatureFlags = {
  admin_agent_enabled: false,
}

export async function getFeatureFlags(): Promise<FeatureFlags> {
  try {
    const response = await fetch("/api/general/v0/system/feature-flags", {
      method: "GET",
      credentials: "same-origin",
    })
    if (!response.ok) return DEFAULT_FLAGS
    const body = await response.json()
    return {
      ...DEFAULT_FLAGS,
      ...body,
    }
  } catch {
    return DEFAULT_FLAGS
  }
}
