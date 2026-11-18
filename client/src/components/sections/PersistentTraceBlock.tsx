/**
 * Phase 45.D — persistent collapsible trace block.
 *
 * Renders below every persisted assistant message in the chat
 * history. Reads `message.metadata.actions` (populated by the
 * backend at end-of-turn) and produces a `<details>` block whose
 * collapsed summary line shows the headline numbers
 * ("Trace — 3 steps · 1.4 s · 600 tokens") and whose expanded
 * body renders the same chip layout the in-flight chip-row uses
 * — reasoning sub-row on top, action chips below.
 *
 * The live in-flight chip-row (`AgentActionRow.tsx`) sits above
 * the streaming bubble during a turn and clears on envelope
 * arrival (EW-44.6). This block is the *persisted* analogue:
 * available on every past message so an operator can replay how
 * the agent answered a question two hours ago.
 *
 * Both rows share the same chip render (`AgentActionRow`-style
 * `<Badge>` markup); the differences are:
 *
 * - This block is per-message + collapsible (defaults closed).
 * - Frames come from `metadata.actions` (in-memory rehydration)
 *   rather than the live Socket.IO stream.
 * - The component is self-contained: no parent state, no event
 *   listeners. Pure render off the persisted shape.
 *
 * Wire contract pinned by
 * `tests/agents/test_persistent_trace_round_trip.py` in
 * project-ask; see `docs/guides/agent-trace-replay.md` for the
 * full design note.
 */

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Trans } from "@lingui/react/macro";
import { PersistedAgentActionFrame } from "@/lib/types/Message";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronRight,
  Clock,
  LoaderCircle,
  Settings2,
} from "lucide-react";
import { ReactNode, useState } from "react";

function PhaseIcon({
  phase,
  tool_name,
}: {
  phase: PersistedAgentActionFrame["phase"];
  tool_name: string;
}): ReactNode {
  if (tool_name === "reasoning") {
    return <Brain className="size-3" aria-hidden />;
  }
  switch (phase) {
    case "summary":
      return <Settings2 className="size-3" aria-hidden />;
    case "start":
      return <LoaderCircle className="size-3" aria-hidden />;
    case "complete":
      return <CheckCircle2 className="size-3" aria-hidden />;
    case "error":
      return <AlertTriangle className="size-3" aria-hidden />;
    case "awaiting_approval":
      // Phase 48.A — persisted trace shows that a HITL pause happened
      // historically. No spinner (the wait is over) — just a clock
      // icon next to the amber styling.
      return <Clock className="size-3" aria-hidden />;
  }
}

function phaseClassname(
  phase: PersistedAgentActionFrame["phase"],
  tool_name: string,
): string {
  if (tool_name === "reasoning") {
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
      return "bg-amber-50 text-amber-900 border-amber-300 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-800";
  }
}

/**
 * Same collapse rule the live chip-row uses: paired
 * (start, complete/error) frames share an id; keep only the
 * latest. Reasoning frames get unique ids per block so they
 * all survive.
 */
function collapseFrames(
  frames: PersistedAgentActionFrame[],
): PersistedAgentActionFrame[] {
  const latestById = new Map<string, PersistedAgentActionFrame>();
  for (const frame of frames) {
    latestById.set(frame.id, frame);
  }
  return Array.from(latestById.values());
}

function compactDuration(ms: number): string {
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)} min`;
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)} s`;
  return `${ms} ms`;
}

function compactTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function TelemetryBadge({ frame }: { frame: PersistedAgentActionFrame }) {
  const parts: string[] = [];
  if (frame.duration_ms !== null && frame.duration_ms !== undefined) {
    parts.push(compactDuration(frame.duration_ms));
  }
  if (
    (frame.tokens_in !== null && frame.tokens_in !== undefined && frame.tokens_in > 0) ||
    (frame.tokens_out !== null && frame.tokens_out !== undefined && frame.tokens_out > 0)
  ) {
    parts.push(
      `${compactTokens(frame.tokens_in ?? 0)} in / ${compactTokens(frame.tokens_out ?? 0)} out`,
    );
  }
  if (parts.length === 0) return null;
  return (
    <span className="ml-1 text-[10px] tabular-nums text-muted-foreground/70 whitespace-nowrap">
      · {parts.join(" · ")}
    </span>
  );
}

/**
 * Phase 48.D — budget-utilisation indicator on the persisted summary
 * chip. The live `AgentActionRow` shows a streaming-forecast badge
 * (`"≈ 1.2k expected"`) DURING streaming; once the turn is done,
 * what the user wants to see in history is "how much of my budget
 * did I actually use" — a percentage of the per-turn ceiling.
 *
 * Renders only when both `meta.max_output_tokens` (the per-turn
 * budget from Phase 47.G) AND a known `tokens_out` are present.
 * Older trace records that pre-date Phase 47.G simply omit the
 * badge.
 *
 * The badge uses amber styling when usage exceeds 80% so a user
 * scrolling through history can spot turns that came close to the
 * ceiling.
 */
function BudgetBadge({
  frame,
  totalTokensOut,
}: {
  frame: PersistedAgentActionFrame;
  /** Total output tokens for the whole turn (from the chat envelope).
   * Per-frame tokens_out on the summary chip is engine-dependent
   * and often null; the envelope total is the authoritative number. */
  totalTokensOut: number;
}) {
  const budget = frame.meta?.max_output_tokens;
  if (typeof budget !== "number" || budget <= 0) return null;
  if (totalTokensOut <= 0) return null;
  // Phase 50.E — no silent clamp. If a turn overshot the configured
  // budget (chunked summary chips that exceed `max_output_tokens` by
  // a multiple) we want the operator to see the real number, not a
  // capped 999% — the warn styling already makes overruns visible at
  // a glance, and 1234% is the actionable signal.
  const pct = Math.round((totalTokensOut / budget) * 100);
  const warn = pct >= 80;
  const over = pct > 100;
  return (
    <span
      className={cn(
        "ml-1 text-[10px] tabular-nums whitespace-nowrap",
        warn ? "text-amber-600 dark:text-amber-400 font-medium" : "text-muted-foreground/70",
      )}
      data-testid="persisted-budget-badge"
      role={over ? "status" : undefined}
      aria-label={
        over
          ? `Output-token budget overrun: ${totalTokensOut} of ${budget} (${pct}%).`
          : `${pct}% of output-token budget used`
      }
      title={`${totalTokensOut} of ${budget} output-token budget used (${pct}%)`}
    >
      · {pct}% of budget
    </span>
  );
}

function ChipBadge({
  frame,
  totalTokensOut,
}: {
  frame: PersistedAgentActionFrame;
  totalTokensOut: number;
}) {
  const isSummary = frame.phase === "summary";
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
      {isSummary && (
        <BudgetBadge frame={frame} totalTokensOut={totalTokensOut} />
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

/**
 * Headline summary line shown in the collapsed `<summary>` element.
 * Formula matches `docs/guides/agent-trace-replay.md` § Cumulative
 * summary line:
 *   Trace — N steps · X.X s · A in / B out · M reasoning stages
 *
 * Token totals come from the chat envelope's
 * `metadata.{input,output}_tokens` since per-tool token attribution
 * is engine-dependent (Phase 45.C accumulates on `TranslatedRun`
 * but per-frame `tokens_in/out` stay null today). Duration is the
 * sum of per-frame `duration_ms` values (null skipped).
 */
function buildSummaryLine(
  frames: PersistedAgentActionFrame[],
  tokensIn: number,
  tokensOut: number,
): string {
  const nonSummary = frames.filter((f) => f.phase !== "summary");
  const reasoning = nonSummary.filter((f) => f.tool_name === "reasoning");
  const actions = nonSummary.filter((f) => f.tool_name !== "reasoning");
  const totalMs = frames.reduce((acc, f) => acc + (f.duration_ms ?? 0), 0);

  const parts: string[] = [];
  parts.push(`${actions.length} step${actions.length === 1 ? "" : "s"}`);
  if (totalMs > 0) parts.push(compactDuration(totalMs));
  if (tokensIn > 0 || tokensOut > 0) {
    parts.push(
      `${compactTokens(tokensIn)} in / ${compactTokens(tokensOut)} out`,
    );
  }
  if (reasoning.length > 0) {
    parts.push(
      `${reasoning.length} reasoning stage${reasoning.length === 1 ? "" : "s"}`,
    );
  }
  return parts.join(" · ");
}

export function PersistentTraceBlock({
  frames,
  tokensIn,
  tokensOut,
}: {
  frames: PersistedAgentActionFrame[];
  tokensIn: number;
  tokensOut: number;
}) {
  const [open, setOpen] = useState(false);
  if (!frames || frames.length === 0) return null;

  const collapsed = collapseFrames(frames);
  const reasoningFrames = collapsed.filter((f) => f.tool_name === "reasoning");
  const actionFrames = collapsed.filter((f) => f.tool_name !== "reasoning");
  const summaryLine = buildSummaryLine(collapsed, tokensIn, tokensOut);

  return (
    <details
      className="mt-2 group border rounded-md text-xs"
      data-testid="persistent-trace-block"
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer select-none px-2 py-1.5 inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground">
        <ChevronRight
          className={cn(
            "size-3 transition-transform",
            open && "rotate-90",
          )}
          aria-hidden
        />
        <Trans>Trace</Trans> — {summaryLine}
      </summary>
      <div className="px-2 pb-2 pt-1 flex flex-col gap-2">
        <TooltipProvider delayDuration={150}>
          {reasoningFrames.length > 0 && (
            <div
              className="flex flex-row flex-wrap gap-2"
              aria-label="agent reasoning trace"
              data-testid="persistent-reasoning-row"
            >
              {reasoningFrames.map((frame) => (
                <ChipBadge key={frame.id} frame={frame} totalTokensOut={tokensOut} />
              ))}
            </div>
          )}
          {actionFrames.length > 0 && (
            <div
              className="flex flex-row flex-wrap gap-2"
              aria-label="agent action trace"
              data-testid="persistent-action-row"
            >
              {actionFrames.map((frame) => (
                <ChipBadge key={frame.id} frame={frame} totalTokensOut={tokensOut} />
              ))}
            </div>
          )}
        </TooltipProvider>
      </div>
    </details>
  );
}
