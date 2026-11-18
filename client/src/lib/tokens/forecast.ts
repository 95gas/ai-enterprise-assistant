/**
 * Phase 47.G — streaming token-forecast math (frontend mirror).
 *
 * Operators see live `tokens_in / tokens_out` per chip (Phase 45.C);
 * what they want for budget-burn awareness is a *projected* total
 * for the in-flight turn so they can read the cost before the model
 * finishes streaming. This module computes that projection from the
 * accumulated streamed-text length on each new
 * `TEXT_MESSAGE_CONTENT` chunk.
 *
 * The math duplicates `src/ask_core/services/agent_actions/forecast.py`
 * in the project-ask backend. The two MUST stay in sync — divergence
 * shows up as a visible chip-badge mismatch when the same accumulated
 * text yields different "≈ 1.2k expected" badges. The reference table
 * `REFERENCE_FORECASTS` is the canonical parity contract; the
 * Python-side test `tests/services/agent_actions/test_forecast.py`
 * exercises the same (chars, ceiling) → projection rows.
 *
 * Math
 * ====
 *
 * 1. `approximateTokensFromChars(chars)`: `chars / 4` floor — a coarse
 *    English-on-average ratio. Multi-byte CJK queries tilt this
 *    slightly low; close enough for a budget-burn hint.
 *
 * 2. `forecastTotalTokens(chars, ceiling)`: applies a length-decay
 *    multiplier so the projection narrows as the stream grows:
 *
 *    chars <  200 → 3.0x   (very early, lots more coming)
 *    chars <  500 → 2.0x
 *    chars < 1000 → 1.4x
 *    chars < 2000 → 1.15x
 *    chars ≥ 2000 → 1.05x
 *
 * 3. Clamp to `ceiling` (the per-turn LLM output budget; read off
 *    `summaryFrame.meta.max_output_tokens` when present, or
 *    `DEFAULT_OUTPUT_CEILING` otherwise).
 *
 * Format
 * ======
 *
 * `formatTokenCount(n)` returns a compact display string:
 *
 *    n <  1_000  →  "543"
 *    n < 10_000  →  "1.2k"
 *    n ≥ 10_000  →  "12k"
 *
 * The chip badge renders `"≈ {formatTokenCount(projected)} expected"`
 * as a small italic suffix after the summary chip's message body.
 */

export const CHARS_PER_TOKEN_APPROX = 4
/** Coarse English approximation used by the chip badge math. Mirrors
 *  the backend's `forecast.CHARS_PER_TOKEN_APPROX`. */

export const DEFAULT_OUTPUT_CEILING = 4096
/** Default per-turn output-tokens ceiling — matches the backend's
 *  `forecast.DEFAULT_OUTPUT_CEILING` (the OpenAI / Anthropic 4k
 *  defaults pinned in the LLM gateway). Used when the summary
 *  frame's `meta.max_output_tokens` is absent on pre-Phase-47.G
 *  deploys. */

export function approximateTokensFromChars(chars: number): number {
  if (!Number.isFinite(chars) || chars <= 0) return 0
  return Math.floor(chars / CHARS_PER_TOKEN_APPROX)
}

function lengthDecayMultiplier(chars: number): number {
  if (chars < 200) return 3.0
  if (chars < 500) return 2.0
  if (chars < 1000) return 1.4
  if (chars < 2000) return 1.15
  return 1.05
}

export function forecastTotalTokens(
  chars: number,
  ceiling: number = DEFAULT_OUTPUT_CEILING,
): number {
  const current = approximateTokensFromChars(chars)
  if (current === 0) return 0
  const projected = Math.floor(current * lengthDecayMultiplier(chars))
  if (projected > ceiling) return ceiling
  if (projected < current) return current
  return projected
}

export function formatTokenCount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0"
  if (n < 1_000) return String(n)
  if (n < 10_000) return `${(n / 1_000).toFixed(1)}k`
  return `${Math.floor(n / 1_000)}k`
}

/**
 * Reference table the React client + Python backend must both
 * produce. Divergence between the two surfaces as a visible chip
 * badge mismatch. Kept in lockstep with the Python module's
 * `REFERENCE_FORECASTS` tuple — when the math is tuned, BOTH
 * tables move together.
 */
export const REFERENCE_FORECASTS: ReadonlyArray<
  readonly [chars: number, ceiling: number, expected: number]
> = [
  [0, 4096, 0],
  [50, 4096, 36],
  [200, 4096, 100],
  [500, 4096, 175],
  [1000, 4096, 287],
  [2000, 4096, 525],
  [5000, 4096, 1312],
  [20_000, 4096, 4096],
]
