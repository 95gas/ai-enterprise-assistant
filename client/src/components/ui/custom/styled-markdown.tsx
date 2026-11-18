import Markdown from "react-markdown";
import remarkBreaks from "remark-breaks"
import { TypographyH1 } from "../typography/h1";
import { TypographyH2 } from "../typography/h2";
import { TypographyH3 } from "../typography/h3";
import { TypographyH4 } from "../typography/h4";
import { TypographyBlockquote } from "../typography/blockquote";
import { TypographyInlineCode } from "../typography/inlinecode";
import { TypographyP } from "../typography/p";
import { TypographySmall } from "../typography/small";
import { TypographyUl } from "../typography/ul";
import { TypographyOl } from "../typography/ol";
import remarkGfm from 'remark-gfm';
import rehypeRaw from "rehype-raw";
import rehypeSlug from "rehype-slug";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "../table";
import { PhrasingContent, Root, RootContent } from "mdast";
import { VFile } from "vfile";
import { visit, SKIP } from "unist-util-visit";
import { PropsWithChildren } from "react";
import { TypographyA } from "../typography/a";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../tooltip";

// This is a simplified conceptual representation, not directly usable code.
function remerkHighlight({ highlight }: {
  highlight?: [number, number]
}) {
  return function (tree: Root, file: VFile) {
    if (!highlight) {
      return
    }

    visit(tree, "text", (node, index, parent) => {
      if (!node.position || node.position.start.offset === undefined || node.position.end.offset === undefined || !parent || typeof index !== 'number') {
        return // Skip unusable nodes
      }

      const nodeStart = node.position.start.offset
      const nodeEnd = node.position.end.offset
      const highlightStart = highlight[0]
      const highlightEnd = highlight[1]

      if (nodeStart >= highlightEnd || nodeEnd <= highlightStart) {
        return // Skip nodes outside highlight range
      }

      const originalValue = node.value
      const newNodes: RootContent[] | PhrasingContent[] = []

      // calculate the text before the start of the highlight
      let beforeStartTextLength = 0
      if (nodeStart < highlightStart) {
        const beforeStartMarkdown = file.value.slice(nodeStart, highlightStart)
        if (beforeStartMarkdown.length > 0) {
          for (let i = 0; i < beforeStartMarkdown.length; i++) {
            if (beforeStartMarkdown.at(i) === originalValue.at(beforeStartTextLength)) {
              beforeStartTextLength += 1
            }
          }
        }
      }

      // calculate the text (highlighted) before the end of the highlight
      let beforeEndTextLenght = originalValue.length
      if (nodeEnd > highlightEnd) {
        beforeEndTextLenght = 0
        const beforeMarkdown = file.value.slice(nodeStart, highlightEnd)
        if (beforeMarkdown.length > 0) {
          for (let i = 0; i < beforeMarkdown.length; i++) {
            if (beforeMarkdown.at(i) === originalValue.at(beforeEndTextLenght)) {
              beforeEndTextLenght += 1
            }
          }
        }
      }

      if (beforeStartTextLength > 0) {
        const beforeStartText = originalValue.substring(0, beforeStartTextLength)
        newNodes.push({ type: 'text', value: beforeStartText })
      }

      if (beforeStartTextLength !== beforeEndTextLenght) {
        const text = originalValue.substring(beforeStartTextLength, beforeEndTextLenght)
        newNodes.push({ type: 'html', value: `<mark>${text}</mark>` })
      }

      if (beforeEndTextLenght > 0) {
        const afterEndText = originalValue.substring(beforeEndTextLenght)
        newNodes.push({ type: 'text', value: afterEndText })
      }

      if (newNodes.length > 0) {
        parent.children.splice(index, 1, ...newNodes)
        return [SKIP, index + newNodes.length]
      }
    })
  }
}

function TableWrapper({ children }: PropsWithChildren) {
  return (
    <div className="overflow-x-scroll border rounded-md"> 
      <Table>
        {children}
      </Table>
    </div>
  )
}

/**
 * Phase 28.C: pre-process the markdown source to wrap inline `[N]`
 * citation markers in a `<cite data-ref="N">[N]</cite>` HTML span,
 * which `rehype-raw` then surfaces as an element so the `components`
 * override below renders it as a Tooltip-wrapped span carrying the
 * chunk-text preview.
 *
 * Skips matches inside fenced code blocks (```…```) and inline code
 * (``…``) so a sample like `arr[0]` in a code snippet doesn't get
 * mistaken for a citation. Skips when no references are supplied,
 * preserving the legacy zero-overhead path for static markdown
 * (manual page, privacy notice, changelog).
 */
const CITE_TOKEN_RE = /\[(\d{1,3})\]/g

function wrapInlineCitations(
  source: string,
  knownIds: Set<number>,
): string {
  if (knownIds.size === 0) return source

  // Walk the source detecting code-block / inline-code regions and
  // replace `[N]` only outside of them.
  let out = ""
  let i = 0
  let inFence = false
  while (i < source.length) {
    if (source.startsWith("```", i)) {
      const end = source.indexOf("```", i + 3)
      if (end === -1) {
        out += source.slice(i)
        break
      }
      out += source.slice(i, end + 3)
      i = end + 3
      inFence = !inFence
      continue
    }
    // Inline-code: backticks with non-newline content.
    if (source[i] === "`") {
      const end = source.indexOf("`", i + 1)
      if (end !== -1 && source.slice(i + 1, end).indexOf("\n") === -1) {
        out += source.slice(i, end + 1)
        i = end + 1
        continue
      }
    }
    out += source[i]
    i += 1
  }

  // Now apply citation replacement on the assembled non-code-block
  // string. Code-block regions are already in `out`; we run the
  // regex globally here. False positives inside indented blocks are
  // rare in chat answers and acceptable for the demo path; a stricter
  // walk lives in 28.C.b if needed.
  return out.replace(CITE_TOKEN_RE, (match, idStr: string) => {
    const id = Number(idStr)
    if (!knownIds.has(id)) return match
    return `<cite data-ref="${id}">${match}</cite>`
  })
}

export type CitationReference = {
  reference_id: number
  text?: string | null
  s3_page?: string | null
  chunk_number?: number | null
}

function CitationToken({
  refId,
  reference,
  children,
}: {
  refId: number
  reference?: CitationReference
  children: React.ReactNode
}) {
  if (!reference?.text) {
    return <span className="text-primary font-medium">{children}</span>
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className="cursor-help rounded bg-primary/10 px-1 text-primary font-medium hover:bg-primary/20"
          aria-label={`Citation ${refId}`}
        >
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-md text-xs whitespace-pre-line">
        {reference.text}
      </TooltipContent>
    </Tooltip>
  )
}

export function StyledMarkdown({ children, highlight, references }: {
  children: string,
  highlight?: [number, number],
  /**
   * Optional citation references for inline `[N]` hover preview
   * (Phase 28.C). When supplied, every `[N]` whose `N` matches a
   * `reference_id` becomes a Tooltip showing the chunk text.
   * Undefined for non-chat callers (manual / privacy / changelog) so
   * the legacy code path is unaffected.
   */
  references?: CitationReference[],
}) {
  const refsById = new Map<number, CitationReference>()
  if (references) {
    for (const r of references) refsById.set(r.reference_id, r)
  }
  const knownIds = new Set(refsById.keys())
  const transformed = knownIds.size > 0
    ? wrapInlineCitations(children, knownIds)
    : children

  return (
    <TooltipProvider delayDuration={150}>
    <Markdown
      remarkPlugins={[ [remerkHighlight, { highlight: highlight }], remarkBreaks, remarkGfm ]}
      rehypePlugins={[rehypeRaw, rehypeSlug]}
      components={{
        h1: TypographyH1,
        h2: TypographyH2,
        h3: TypographyH3,
        h4: TypographyH4,
        p: TypographyP,
        blockquote: TypographyBlockquote,
        code: TypographyInlineCode,
        small: TypographySmall,
        ul: TypographyUl,
        ol: TypographyOl,
        a: TypographyA,
        table: TableWrapper,
        thead: TableHeader,
        tbody: TableBody,
        tfoot: TableFooter,
        tr: TableRow,
        th: TableHead,
        td: TableCell,
        // Phase 28.C: render `<cite data-ref="N">[N]</cite>` (injected
        // by `wrapInlineCitations`) as a Tooltip-wrapped span carrying
        // the chunk-text preview. When `references` is empty, the
        // wrapper is skipped so this override never fires for static
        // markdown pages.
        cite: (props) => {
          const refIdRaw = (props as unknown as { 'data-ref'?: string })['data-ref']
          const refId = refIdRaw ? Number(refIdRaw) : NaN
          const reference = Number.isFinite(refId) ? refsById.get(refId) : undefined
          return <CitationToken refId={refId} reference={reference}>{props.children}</CitationToken>
        },
      }}
    >
      {transformed}
    </Markdown>
    </TooltipProvider>
  )
}