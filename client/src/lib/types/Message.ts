import { Source } from "./Chat"
import { Document } from "./Document"

export enum MessageRole {
  User = "user",
  Assistant = "assistant"
}

export enum MessageMode {
  Chat = "chat",
  Focus = "focus"
}

/**
 * Workflow values accepted by the backend's chat-invoke router.
 *
 * Phase 27.B+C.1: this is the wire-level identity of which agent
 * handles a turn. The legacy client only ever surfaced QA + FocusMode;
 * the four specialised App agents (`Report`, `UserSupport`,
 * `DeepResearch` [renamed from `AllForOne` in Phase 51.B; the legacy
 * literal stays for one phase of soft-deprecation], `ExampleQuestions`)
 * shipped server-side in Phase 15 but stayed invisible until now.
 *
 * `MessageMode` (above) is the persisted-message shape, kept binary
 * (Chat | Focus) so messages already in storage round-trip unchanged.
 * We auto-derive `mode = workflow === "FocusMode" ? Focus : Chat` on
 * send.
 */
export type Workflow =
  | "QA"
  | "FocusMode"
  | "Report"
  | "UserSupport"
  // Phase 51.B — `DeepResearch` is the canonical name (was
  // `AllForOne`). The legacy literal stays in the union for one
  // phase of soft-deprecation so old persisted messages still
  // type-check.
  | "DeepResearch"
  | "AllForOne"
  | "ExampleQuestions"
  // Phase 49.F shipped the backend; Phase 50.A wires it into the
  // workflow picker. Doubly-gated client-side: only rendered when
  // the operator has flipped `ASK_ADMIN_AGENT_ENABLED=1` (surfaced
  // via `GET /api/general/v0/system/feature-flags`) AND the user
  // holds an `admin:*` group.
  | "AdminAssistant"
  // Phase 59.C — user-scoped general orchestrator. Phase 59.G makes
  // this the chat client's default (the workflow dropdown is gone).
  | "General"

/** Workflow values that every user can pick (no extra RBAC gate).
 *  Phase 51.B — `DeepResearch` replaces `AllForOne` in the picker
 *  dropdown; the legacy literal is not surfaced. */
export const PUBLIC_WORKFLOWS: ReadonlyArray<Workflow> = [
  "QA",
  "FocusMode",
  "Report",
  "UserSupport",
  "DeepResearch",
  "ExampleQuestions",
]

/** Workflow values that require an admin:* group + a server-side
 *  feature flag to render in the picker. Phase 50.A. */
export const ADMIN_WORKFLOWS: ReadonlyArray<Workflow> = ["AdminAssistant"]

/** All workflow values, in display order for the dropdown.
 *  Kept for callers that want the full set without RBAC filtering
 *  (e.g. type checks, test fixtures). */
export const WORKFLOWS: ReadonlyArray<Workflow> = [
  ...PUBLIC_WORKFLOWS,
  ...ADMIN_WORKFLOWS,
]

/** Default workflow for new chat sessions. Phase 59.G — switched
 *  from `QA` to `General` so the user-scoped orchestrator picks up
 *  every new chat by default; the workflow dropdown is retired. */
export const DEFAULT_WORKFLOW: Workflow = "General"

export function workflowToMode(workflow: Workflow): MessageMode {
  return workflow === "FocusMode" ? MessageMode.Focus : MessageMode.Chat
}

export type UserMessage = {
  role: MessageRole.User
  content: string
  llm_model: string,
  provider: string,
  mode: MessageMode,
  documents: Document[]
}

/**
 * Phase 45.D — `metadata.actions` carries the per-turn
 * `agent-action` frame snapshot the runtime stamped on the
 * persisted assistant message. React's `PersistentTraceBlock`
 * renders these as a collapsible chip history on every past
 * assistant message; the live in-flight chip-row above the
 * streaming bubble is separate and clears on envelope arrival.
 *
 * Per-frame shape mirrors the live-wire `AgentActionFrame`
 * minus the `type: "agent-action"` discriminator (implicit
 * because the whole array is agent-action frames). Phase 45.C
 * telemetry fields (`tokens_in`, `tokens_out`, `duration_ms`)
 * are always present with `null` when unknown.
 */
export type PersistedAgentActionFrame = {
  // Phase 48.A — `awaiting_approval` joins the persisted phase set
  // so the forensic-replay surface records that an HITL pause
  // happened. The matching resolution frame (complete / error)
  // shares the same correlation id and lands later in the list.
  phase: "summary" | "start" | "complete" | "error" | "awaiting_approval"
  id: string
  tool_name: string
  label: string
  message: string
  detail: string | null
  language: "en" | "it" | "zh"
  ts: string
  tokens_in: number | null
  tokens_out: number | null
  duration_ms: number | null
  meta: Record<string, unknown>
}

export type AssistantMessage = {
  role: MessageRole.Assistant
  content: string
  sources?: Source[]
  recorded_notes?: Record<string, string>
  metadata: {
    input_tokens: number
    output_tokens: number
    llm_model: string
    chat_name?: string
    /** Phase 45.D — per-turn `agent-action` frame snapshot
     *  rehydrated for the collapsible persistent-trace block. */
    actions?: PersistedAgentActionFrame[]
  }
}

export type SystemMessage = {
  role: "system"
}

export type Message = UserMessage | AssistantMessage