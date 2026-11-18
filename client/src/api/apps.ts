/**
 * Phase 59.D — apps endpoint client.
 *
 * `GET /api/general/v0/apps` returns the union of app-specific
 * manifests visible to the caller (visibility-groups ∩ user.groups).
 * The Phase 59.G Apps sidebar renders one tile per entry.
 */

export type AppSummary = {
  id: string
  name: string
  workflow: string
  description: string
  visibility_groups: string[]
}

export async function getVisibleApps(): Promise<AppSummary[]> {
  try {
    const response = await fetch("/api/general/v0/apps", {
      method: "GET",
      credentials: "same-origin",
    })
    if (!response.ok) return []
    const body = await response.json()
    return Array.isArray(body) ? (body as AppSummary[]) : []
  } catch {
    return []
  }
}
