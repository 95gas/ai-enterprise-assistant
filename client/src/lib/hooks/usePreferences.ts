/**
 * Fetch + cache the user's server-side preferences (Phase 28.B).
 *
 * Phase 27.B+C.5 shipped the backend (`GET /api/general/v0/settings/preferences`)
 * and the Settings page that writes it. Phase 28.B closes the loop by
 * reading those values on chat-page mount so a saved
 * `default_workflow` actually drives the dropdown's initial state, and
 * a saved `preferred_model` is the auto-pick on the model selector
 * (when it's still within token budget — the budget gate stays the
 * source of truth).
 *
 * Caching: a single in-flight Promise per page lifetime, deduplicated
 * across `<ChatPage>` + `<AskPage>` instances. The hook returns
 * `loaded === false` until the first fetch resolves; pages should
 * gate their initial-state writes on it so a paint with the wrong
 * initial value doesn't briefly flash.
 */

import { useEffect, useState } from "react"
import { Workflow } from "@/lib/types/Message"

export type Preferences = {
  default_workflow?: Workflow
  ui_language?: "en" | "it" | "zh"
  preferred_model?: string
}

let cachedPromise: Promise<Preferences> | null = null

function fetchPreferencesOnce(): Promise<Preferences> {
  if (cachedPromise) return cachedPromise
  cachedPromise = (async () => {
    try {
      const res = await fetch("/api/general/v0/settings/preferences", {
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
      })
      if (!res.ok) {
        console.warn(
          `usePreferences: backend returned ${res.status}; falling back to empty prefs`,
        )
        return {}
      }
      return (await res.json()) as Preferences
    } catch (err) {
      console.warn("usePreferences: fetch failed", err)
      return {}
    }
  })()
  return cachedPromise
}

/**
 * Drop the cached prefs (call after the user saves new preferences so
 * other pages re-fetch fresh values on their next mount).
 */
export function invalidatePreferencesCache(): void {
  cachedPromise = null
}

export function usePreferences(): { prefs: Preferences; loaded: boolean } {
  const [prefs, setPrefs] = useState<Preferences>({})
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchPreferencesOnce().then((p) => {
      if (!cancelled) {
        setPrefs(p)
        setLoaded(true)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  return { prefs, loaded }
}
