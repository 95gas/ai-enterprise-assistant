/**
 * Phase 44 — Agent action chip row.
 *
 * Renders the live `agent-action` frames the backend pushes onto the
 * `chat-{chatId}` Socket.IO channel as a horizontal row of chips
 * above the streaming assistant bubble. Each chip shows the
 * lifecycle phase (start / complete / error) + a localised
 * `message`; hover shows the truncated `detail` excerpt when one
 * lands on the complete frame.
 *
 * Phase 44 round-4 (EW-44.17): `tool_name="reasoning"` chips are
 * split out into a separate "Thinking…" surface above the action
 * row. Reasoning frames come from two sources:
 *
 * 1. Engine pipeline-stage events (`kind: "reasoning"` from
 *    mirai-agent-core's `engine.py`/`orchestrator.py`).
 * 2. `<think>…</think>` blocks the runtime extracts from the
 *    streamed LLM text BEFORE shipping the user-facing answer.
 *
 * The two-row layout (safe progress summaries on top, actions
 * below) keeps user-facing status separate from the answer body.
 *
 * The component is purely presentational — the parent
 * (`ChatPage.tsx` / `AskPage.tsx`) owns the in-flight frame list and
 * clears it when the closing envelope lands (EW-44.6).
 *
 * Wire shape: [`AgentActionFrame`][../../lib/types/AgentAction.ts].
 */

import { resolveApproval } from "@/api/chat";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DEFAULT_OUTPUT_CEILING,
  forecastTotalTokens,
  formatTokenCount,
} from "@/lib/tokens/forecast";
import { AgentActionFrame, AgentActionPhase } from "@/lib/types/AgentAction";
import { cn } from "@/lib/utils";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import {
  AlertTriangle,
  Brain,
  Check,
  CheckCircle2,
  Clock,
  LoaderCircle,
  Settings2,
  X,
} from "lucide-react";
import { ReactNode, useState } from "react";
import { toast } from "sonner";

/**
 * Visual styling for each lifecycle phase.
 *
 * `start` frames use a spinner so the chip clearly reads as in-flight;
 * `complete` chips use a checkmark; `error` chips use a warning
 * triangle and the `destructive` Tailwind class. `summary` chips use
 * a small settings icon to indicate "active toggle state for this
 * turn". Reasoning chips (Phase 44 round-4) use a brain icon and
 * never spin — they are emitted with phase=complete after the
 * runtime has finished extracting the block.
 */
function PhaseIcon({
  phase,
  tool_name,
}: {
  phase: AgentActionPhase;
  tool_name: string;
}): ReactNode {
  if (tool_name === "reasoning") {
    return <Brain className="size-3" aria-hidden />;
  }
  switch (phase) {
    case "summary":
      return <Settings2 className="size-3" aria-hidden />;
    case "start":
      return <LoaderCircle className="size-3 animate-spin" aria-hidden />;
    case "complete":
      return <CheckCircle2 className="size-3" aria-hidden />;
    case "error":
      return <AlertTriangle className="size-3" aria-hidden />;
    case "awaiting_approval":
      // Phase 48.A — clock icon (no spinner) so the chip reads as
      // "stalled waiting for a human", not "still working".
      return <Clock className="size-3" aria-hidden />;
  }
}

function phaseClassname(
  phase: AgentActionPhase,
  tool_name: string,
): string {
  if (tool_name === "reasoning") {
    // Distinct italic + lighter visual so the user reads it as
    // "thinking, not the answer". The dashed border + low-contrast
    // text matches Claude.ai / ChatGPT's reasoning-row treatment.
    return "border-dashed bg-muted/30 text-muted-foreground italic";
  }
  switch (phase) {
    case "summary":
      return "border-dashed bg-muted/40";
    case "start":
      return "bg-muted/60";
    case "complete":
      return "bg-muted/40 text-muted-foreground";
    case "error":
      return "bg-destructive/15 text-destructive border-destructive/30";
    case "awaiting_approval":
      // Phase 48.A — amber styling (not destructive) so the chip
      // signals "action required" without reading as failure. Border
      // is solid + slightly brighter than start chips to draw the
      // eye to the inline Approve / Deny buttons.
      return "bg-amber-50 text-amber-900 border-amber-300 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-800";
  }
}

/**
 * Phase 48.A — inline Approve / Deny action buttons rendered next to
 * the chip body. POSTs to
 * `/api/general/v0/chats/{chatId}/approvals/{taskId}` and disables
 * itself optimistically while in-flight. The chip itself stays in
 * `awaiting_approval` until the backend's `emit_hitl_resolved` lands
 * (the chip-row's frame-collapse logic flips it to complete/error in
 * place via the shared correlation id).
 */
function HITLActionButtons({
  chatId,
  frame,
}: {
  chatId: string | undefined;
  frame: AgentActionFrame;
}) {
  const [busy, setBusy] = useState(false);
  const taskId = typeof frame.meta?.task_id === "string" ? frame.meta.task_id : null;
  if (!chatId || !taskId) return null;

  const decide = async (confirmed: boolean) => {
    setBusy(true);
    const verb = confirmed ? t`approving` : t`denying`;
    try {
      const result = await resolveApproval(chatId, taskId, confirmed);
      if (!result.resolved) {
        if (result.status === 409) {
          toast.info(t`Approval already resolved.`);
        } else if (result.status === 404) {
          toast.error(t`Approval task not found.`);
        } else {
          toast.error(t`Failed to resolve approval (${result.status}).`);
        }
        return;
      }
      toast.success(
        confirmed ? t`Approved — running the tool…` : t`Denied — refused.`,
      );
    } catch (err) {
      console.error(`Error ${verb} approval:`, err);
      toast.error(t`Network error while resolving approval.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className="ml-1 inline-flex items-center gap-1" data-testid="hitl-actions">
      <Button
        size="sm"
        variant="outline"
        className="h-5 px-1.5 py-0 text-[10px] gap-0.5 border-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900/40"
        disabled={busy}
        onClick={() => decide(true)}
        aria-label="Approve tool call"
      >
        <Check className="size-3" aria-hidden />
        <Trans>Approve</Trans>
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="h-5 px-1.5 py-0 text-[10px] gap-0.5 border-amber-400 hover:bg-destructive/10"
        disabled={busy}
        onClick={() => decide(false)}
        aria-label="Deny tool call"
      >
        <X className="size-3" aria-hidden />
        <Trans>Deny</Trans>
      </Button>
    </span>
  );
}

/**
 * Collapse the per-turn frame list to one chip per correlation id.
 *
 * The backend emits paired `start` ↔ `complete` (or `error`) frames
 * that share an `id` — we keep only the latest frame per id so a
 * fast tool call renders as a single chip rather than a flash of
 * "Searching…" followed instantly by "Found 5 results".
 *
 * Reasoning chips (Phase 44 round-4) always have unique ids
 * (each `<think>` block + each engine reasoning event gets its
 * own id), so they all survive the collapse — multiple reasoning
 * steps render as multiple chips in chronological order.
 *
 * Summary frames have a unique id with no companion and are kept
 * as-is. Insertion order is preserved so the chip row reads
 * chronologically from left to right.
 */
function collapseFrames(frames: AgentActionFrame[]): AgentActionFrame[] {
  const latestById = new Map<string, AgentActionFrame>();
  for (const frame of frames) {
    latestById.set(frame.id, frame);
  }
  return Array.from(latestById.values());
}

/**
 * Phase 45.C — render a compact "1.4 s · 234 in / 467 out" telemetry
 * badge to the right of the chip text when the frame carries the
 * Phase 45.C wire fields. Returns null when neither duration nor
 * tokens are populated so older / lighter chips stay unchanged.
 */
function TelemetryBadge({ frame }: { frame: AgentActionFrame }) {
  const parts: string[] = [];
  if (frame.duration_ms !== null && frame.duration_ms !== undefined) {
    if (frame.duration_ms >= 1000) {
      parts.push(`${(frame.duration_ms / 1000).toFixed(1)} s`);
    } else {
      parts.push(`${frame.duration_ms} ms`);
    }
  }
  if (
    (frame.tokens_in !== null && frame.tokens_in !== undefined && frame.tokens_in > 0) ||
    (frame.tokens_out !== null && frame.tokens_out !== undefined && frame.tokens_out > 0)
  ) {
    const tin = frame.tokens_in ?? 0;
    const tout = frame.tokens_out ?? 0;
    parts.push(`${tin} in / ${tout} out`);
  }
  if (parts.length === 0) return null;
  return (
    <span
      className="ml-1 text-[10px] tabular-nums text-muted-foreground/70 whitespace-nowrap"
      data-testid="agent-action-telemetry"
    >
      · {parts.join(" · ")}
    </span>
  );
}

/**
 * Phase 47.G — italic "≈ 1.2k expected" forecast suffix.
 *
 * Rendered on the summary chip ONLY (`phase === "summary"`), and ONLY
 * while the assistant is still streaming. Reads the streamed-text
 * char count + the per-turn output-token ceiling off the summary
 * frame's `meta.max_output_tokens` (falls back to
 * `DEFAULT_OUTPUT_CEILING` on pre-Phase-47.G deploys).
 */
function ForecastBadge({
  streamingChars,
  ceiling,
}: {
  streamingChars: number;
  ceiling: number;
}) {
  // The parent `AgentActionRow` quantises `streamingChars` to 200-char
  // buckets (Math.floor(text.length / 200) * 200), so this child only
  // sees values ≥ 200 once any meaningful streaming has started. The
  // `<= 0` guard below covers the pre-stream and zero-projection cases.
  const projected = forecastTotalTokens(streamingChars, ceiling);
  if (projected <= 0) return null;
  return (
    <span
      className="ml-1 text-[10px] italic tabular-nums text-muted-foreground/70 whitespace-nowrap"
      data-testid="agent-action-forecast"
    >
      · ≈ {formatTokenCount(projected)} expected
    </span>
  );
}

function ChipBadge({
  frame,
  streamingChars,
  chatId,
}: {
  frame: AgentActionFrame;
  /** Length of the in-flight streamed assistant text. Only used to
   *  render the forecast badge on the summary chip; ignored
   *  otherwise. */
  streamingChars: number;
  /** Phase 48.A — chat id, used to route HITL approval POSTs. */
  chatId?: string;
}) {
  const isSummary = frame.phase === "summary";
  const isAwaitingApproval = frame.phase === "awaiting_approval";
  const ceiling =
    (typeof frame.meta?.max_output_tokens === "number" &&
      frame.meta.max_output_tokens > 0 &&
      frame.meta.max_output_tokens) ||
    DEFAULT_OUTPUT_CEILING;
  const chip = (
    <Badge
      variant="outline"
      className={cn(
        "px-2 py-1 text-xs font-normal inline-flex items-center gap-1.5 max-w-full",
        phaseClassname(frame.phase, frame.tool_name),
      )}
      data-phase={frame.phase}
      data-tool={frame.tool_name || "summary"}
    >
      <PhaseIcon phase={frame.phase} tool_name={frame.tool_name} />
      <span className="truncate" style={{ overflowWrap: "anywhere" }}>
        {frame.message}
      </span>
      <TelemetryBadge frame={frame} />
      {isSummary && streamingChars > 0 && (
        <ForecastBadge streamingChars={streamingChars} ceiling={ceiling} />
      )}
      {isAwaitingApproval && (
        <HITLActionButtons chatId={chatId} frame={frame} />
      )}
    </Badge>
  );
  if (!frame.detail) return chip;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{chip}</TooltipTrigger>
      <TooltipContent side="top" className="text-xs max-w-md break-words">
        {frame.detail}
      </TooltipContent>
    </Tooltip>
  );
}

export function AgentActionRow({
  frames,
  loading,
  streamingText,
  chatId,
}: {
  /** Append-only list of frames received this turn. */
  frames: AgentActionFrame[];
  /** When `true`, the assistant bubble is still streaming so the
   *  row stays visible even after the last `complete` chip lands. */
  loading: boolean;
  /**
   * Phase 47.G — the in-flight assistant text buffer. Char-length
   * drives the streaming token-forecast badge on the summary chip
   * (`"≈ 1.2k expected"`). Pass `undefined` (the default) to keep
   * the pre-47.G chip-row layout unchanged.
   */
  streamingText?: string;
  /**
   * Phase 48.A — chat id; threaded into HITL chips so the inline
   * Approve / Deny buttons route their POST to the right chat.
   * Optional so older / non-chat surfaces that render the chip-row
   * (e.g. forensic-replay) stay backward-compatible without the
   * action affordance.
   */
  chatId?: string;
}) {
  if (!loading && frames.length === 0) return null;
  const collapsed = collapseFrames(frames);
  if (collapsed.length === 0) return null;

  // Phase 44 round-4 (EW-44.17) — split reasoning chips into their
  // own row above the action chips. The user reads "Thinking…"
  // narration first, then "Actions" (summary / tool calls).
  const reasoningFrames = collapsed.filter(
    (f) => f.tool_name === "reasoning",
  );
  const actionFrames = collapsed.filter(
    (f) => f.tool_name !== "reasoning",
  );

  // Phase 47.G — quantise the streaming length to 200-char buckets
  // so the forecast badge updates 5×/typical-turn instead of
  // 100×/typical-turn. The collapseFrames step already dedupes by
  // id; this caps the recompute frequency for the `ForecastBadge`
  // child and prevents thrashing while the user reads the chip.
  const streamingChars =
    loading && streamingText
      ? Math.floor(streamingText.length / 200) * 200
      : 0;

  return (
    <div className="flex flex-col gap-2 -mb-2" data-testid="agent-action-row">
      <TooltipProvider delayDuration={150}>
        {reasoningFrames.length > 0 && (
          <div
            className="flex flex-row flex-wrap gap-2"
            aria-label="agent reasoning stream"
            data-testid="agent-reasoning-row"
          >
            {reasoningFrames.map((frame) => (
              <ChipBadge
                key={frame.id}
                frame={frame}
                streamingChars={0}
                chatId={chatId}
              />
            ))}
          </div>
        )}
        {actionFrames.length > 0 && (
          <div
            className="flex flex-row flex-wrap gap-2"
            aria-label="agent action stream"
          >
            {actionFrames.map((frame) => (
              <ChipBadge
                key={frame.id}
                frame={frame}
                streamingChars={streamingChars}
                chatId={chatId}
              />
            ))}
          </div>
        )}
      </TooltipProvider>
    </div>
  );
}

export default AgentActionRow;
