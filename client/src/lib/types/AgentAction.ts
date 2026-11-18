/**
 * Phase 44 / ADR-0059 — wire-shape for `agent-action` frames.
 *
 * The backend pushes one or more frames onto the existing
 * `chat-{chatId}` Socket.IO channel during a turn. Each frame carries
 * the lifecycle stage (`summary` / `start` / `complete` / `error`),
 * a stable `id` correlating `start` ↔ `complete`, and the
 * user-language `label` + `message` strings the chip renders.
 *
 * `tool_name` is the raw engine token — the React client uses
 * `label` + `message` for display and `tool_name` only for grouping
 * + analytics.
 *
 * Additive: the existing text-stream + final-envelope frames on the
 * same channel are unchanged. Old clients that only listen for
 * strings + the closing envelope simply ignore these.
 */
export type AgentActionPhase =
  | "summary"
  | "start"
  | "complete"
  | "error"
  // Phase 48.A — HITL approval surfacing. A HITL-gated tool call that
  // blocks on operator approval emits this phase BEFORE blocking.
  // The chip renders Approve / Deny inline action buttons that POST
  // to `/api/general/v0/chats/{chatId}/approvals/{taskId}`. The
  // matching resolution emit reuses the same correlation id and
  // collapses onto this chip with phase=complete (approved) or
  // phase=error (denied / timeout).
  | "awaiting_approval";

export type AgentActionFrame = {
  type: "agent-action";
  phase: AgentActionPhase;
  /** UUID-shaped correlation id; `start` and its `complete`/`error` share one. */
  id: string;
  /** Engine-side tool name (`web_search`, `agentic_rag`, …) or empty for `summary`. */
  tool_name: string;
  /** Localised short category label (`Web search`, `Knowledge search`, …). */
  label: string;
  /** Localised user-facing message rendered as the chip body. */
  message: string;
  /** Optional sanitised tool-output excerpt (≤ 300 chars, runs through
   *  `InternalNamingGuard`). `null` for `summary` / `start` frames. */
  detail: string | null;
  /** Per-language template key (`en` / `it` / `zh`). */
  language: "en" | "it" | "zh";
  /** ISO-8601 UTC; ms-precision. */
  ts: string;
  /**
   * Phase 45.C telemetry fields. Always present on the wire (null
   * when unknown). React renders compact badges to the right of
   * the chip message when populated:
   *
   *   1.4 s · 234 in / 467 out
   *
   * `tokens_in` / `tokens_out` carry the engine-emitted per-call
   * token count when available; today the engine emits totals at
   * end-of-turn so per-tool numbers stay null and the summary
   * frame at the start of the row carries the cumulative pair.
   * `duration_ms` is the wall-clock from the matching `start`
   * frame to this `complete` / `error` frame; null on `start` and
   * `summary` frames.
   */
  tokens_in: number | null;
  tokens_out: number | null;
  duration_ms: number | null;
  /**
   * Reserved for additive future fields. Frontend ignores unknown keys.
   *
   * Phase 47.G — when the frame is `phase: "summary"`, the backend
   * stamps `meta.max_output_tokens` with the per-turn LLM output
   * budget. The chip-row uses it as the ceiling for the
   * `"≈ 1.2k expected"` streaming-forecast badge. Older pre-47.G
   * deploys omit the key; the client falls back to the local
   * `DEFAULT_OUTPUT_CEILING` constant.
   */
  meta: Record<string, unknown> & {
    max_output_tokens?: number
    // Phase 48.A — HITL chip wire fields. Present on `awaiting_approval`
    // frames AND on the matching resolution frame so the client can
    // route the POST to the right endpoint and read the final outcome.
    task_id?: string
    approval_url?: string
    hitl?: boolean
    hitl_outcome?: "approved" | "denied" | "timeout"
  };
};

/**
 * Type guard used by the chat-stream listener to distinguish action
 * frames from the legacy string text-chunks + final-envelope dicts.
 */
export function isAgentActionFrame(payload: unknown): payload is AgentActionFrame {
  return (
    typeof payload === "object" &&
    payload !== null &&
    (payload as { type?: unknown }).type === "agent-action"
  );
}
