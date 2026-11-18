import Navigation from "@/components/ui/custom/navigation"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Route } from "@/lib/types/Route"
import { Settings } from "lucide-react"
import { Trans } from "@lingui/react/macro"
import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Workflow, WORKFLOWS } from "@/lib/types/Message"
import { toast } from "sonner"
import { t } from "@lingui/core/macro"
import { useLingui } from "@lingui/react/macro"
import { dynamicActivate } from "@/i18n"
import { invalidatePreferencesCache } from "@/lib/hooks/usePreferences"

type Preferences = {
  default_workflow?: Workflow
  ui_language?: "en" | "it" | "zh"
  preferred_model?: string
}

async function fetchPreferences(): Promise<Preferences> {
  const res = await fetch("/api/general/v0/settings/preferences", {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function savePreferences(prefs: Preferences): Promise<Preferences> {
  // Strip empty strings so the body matches the backend's exclude_none semantics.
  const body: Preferences = {}
  if (prefs.default_workflow) body.default_workflow = prefs.default_workflow
  if (prefs.ui_language) body.ui_language = prefs.ui_language
  if (prefs.preferred_model && prefs.preferred_model.trim()) {
    body.preferred_model = prefs.preferred_model.trim()
  }
  const res = await fetch("/api/general/v0/settings/preferences", {
    method: "PUT",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => null)
    throw new Error(err?.error?.message ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}

const WORKFLOW_LABELS: Record<Workflow, string> = {
  QA: "QA",
  FocusMode: "Focus on docs",
  Report: "Report",
  UserSupport: "User support",
  // Phase 51.B — canonical name + legacy alias both render the new
  // user-facing label so an old persisted message still shows the
  // right text in the settings UI.
  DeepResearch: "Deep research",
  AllForOne: "Deep research",
  ExampleQuestions: "Example questions",
  AdminAssistant: "Admin assistant",
  General: "General assistant",
}

const LANGUAGES = [
  { id: "en" as const, label: "English" },
  { id: "it" as const, label: "Italiano" },
  { id: "zh" as const, label: "中文" },
]

function SettingsPage() {
  const { i18n } = useLingui()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [prefs, setPrefs] = useState<Preferences>({})

  useEffect(() => {
    let cancelled = false
    fetchPreferences()
      .then((p) => {
        if (!cancelled) setPrefs(p)
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("Failed to load preferences", err)
          toast.error(t`Failed to load settings: ${err.message ?? err}`)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const onSave = async () => {
    setSaving(true)
    try {
      const saved = await savePreferences(prefs)
      setPrefs(saved)
      // Persist the language client-side too so the i18n provider picks
      // it up on next reload (the backend's `ui_language` is the source
      // of truth across devices; localStorage is the fast read on boot).
      if (saved.ui_language) {
        localStorage.setItem("vite-ui-locale", saved.ui_language)
        await dynamicActivate(saved.ui_language)
      }
      // Phase 28.B: drop the module-level prefs cache so ChatPage /
      // AskPage instances mounted next pick up the new defaults.
      invalidatePreferencesCache()
      toast.success(t`Settings saved`)
    } catch (err) {
      toast.error(t`Failed to save: ${(err as Error).message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="w-full flex flex-col h-screen">
      <Navigation />
      <main className="h-full overflow-hidden">
        <ScrollArea className="w-full h-full">
          <div className="w-full flex justify-center">
            <div className="max-w-[48rem] w-full p-4 grid gap-4">
              <Card className="mt-20">
                <CardHeader>
                  <CardTitle>
                    <Trans>Settings</Trans>
                  </CardTitle>
                  <CardDescription>
                    <Trans>
                      User-controlled preferences. Saved server-side under your account so they
                      follow you across devices.
                    </Trans>
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-6">
                  {loading ? (
                    <p className="text-sm text-muted-foreground">
                      <Trans>Loading…</Trans>
                    </p>
                  ) : (
                    <>
                      <div className="grid gap-2">
                        <Label>
                          <Trans>Default workflow</Trans>
                        </Label>
                        <Select
                          value={prefs.default_workflow ?? ""}
                          onValueChange={(value) =>
                            setPrefs({ ...prefs, default_workflow: value as Workflow })
                          }
                        >
                          <SelectTrigger className="w-64">
                            <SelectValue placeholder={t`Select workflow`} />
                          </SelectTrigger>
                          <SelectContent>
                            {WORKFLOWS.map((w) => (
                              <SelectItem key={w} value={w}>
                                {WORKFLOW_LABELS[w]}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                          <Trans>
                            New chats start with this workflow selected. You can switch per-chat
                            from the dropdown next to the model selector.
                          </Trans>
                        </p>
                      </div>

                      <div className="grid gap-2">
                        <Label>
                          <Trans>UI language</Trans>
                        </Label>
                        <Select
                          value={prefs.ui_language ?? i18n.locale}
                          onValueChange={(value) =>
                            setPrefs({ ...prefs, ui_language: value as Preferences["ui_language"] })
                          }
                        >
                          <SelectTrigger className="w-64">
                            <SelectValue placeholder={t`Select language`} />
                          </SelectTrigger>
                          <SelectContent>
                            {LANGUAGES.map((l) => (
                              <SelectItem key={l.id} value={l.id}>
                                {l.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="grid gap-2">
                        <Label>
                          <Trans>Preferred model (provider/model)</Trans>
                        </Label>
                        <input
                          type="text"
                          value={prefs.preferred_model ?? ""}
                          onChange={(e) => setPrefs({ ...prefs, preferred_model: e.target.value })}
                          placeholder="openai/gpt-4o-mini"
                          maxLength={128}
                          className="w-64 rounded-md border bg-transparent px-3 py-2 text-sm"
                        />
                        <p className="text-xs text-muted-foreground">
                          <Trans>
                            New chats default to this model when it's available within your token
                            budget. Per-chat overrides still work.
                          </Trans>
                        </p>
                      </div>

                      <div className="flex gap-2">
                        <Button onClick={onSave} disabled={saving}>
                          {saving ? <Trans>Saving…</Trans> : <Trans>Save</Trans>}
                        </Button>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </ScrollArea>
      </main>
    </div>
  )
}

const SettingsRoute: Route = {
  path: "settings",
  element: <SettingsPage />,
  handle: {
    getPageName: () => <Trans>Settings</Trans>,
    getPageSidebar: () => ({
      group: "information",
      icon: <Settings className="h-4 w-4" />,
    }),
  },
}

export default SettingsRoute
