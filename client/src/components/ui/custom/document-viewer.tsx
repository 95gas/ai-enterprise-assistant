import { ScrollArea, ScrollBar } from "../scroll-area"
import { Button } from "../button"
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { StyledMarkdown } from "./styled-markdown"
import { Skeleton } from "../skeleton"
import { Document } from "@/lib/types/Document"
import { ToggleGroup, ToggleGroupItem } from "../toggle-group"
import { t } from "@lingui/core/macro"
import { Trans } from "@lingui/react/macro"
import { DocumentSource } from "@/lib/types/Chat"

// enum FileType {
//   PDF = ".pdf",
//   Markdown = ".md",
//   Text = ".txt",
//   Excel = ".xlsx",
// }

function MarkdownRenderer({ s3Bucket, s3Path, filename, pages, setPages, pageNumber, highlight, scrollAreaRef }: {
  s3Bucket: Document['s3_bucket'],
  s3Path: Document['s3_path'],
  filename: Document['filename'],
  pages: string[],
  setPages: (pages: string[]) => void,
  pageNumber: number,
  highlight?: [number, number],
  scrollAreaRef: React.RefObject<HTMLDivElement>
}) {
  const [markdownContent, setMarkdownContent] = useState("")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const loadPages = async () => {
      setLoading(true) 
      const response = await fetch(`/api/general/v0/docs/${s3Bucket}/${encodeURIComponent(s3Path)}/${encodeURIComponent(filename)}`)
      if (response.ok) {
        const body = await response.json()
        setPages(Object.values(body))
      } else {
        setMarkdownContent(t`Error loading the document`)
      }
      setLoading(false)
    }

    loadPages()
  }, [s3Bucket, s3Path, filename, setPages])

  useEffect(() => {
    const loadPage = async () => {
      setLoading(true)
      const params = new URLSearchParams({s3_page: pages[pageNumber - 1]})
      const response = await fetch(`/api/general/v0/docs/${s3Bucket}/${encodeURIComponent(s3Path)}/${encodeURIComponent(filename)}?${params.toString()}`)
      if (response.ok) {
        const text = await response.text()
        setMarkdownContent(text)
      } else {
        setMarkdownContent(t`Error loading the document`)
      }
      setLoading(false)
    }

    if (pages.length >= 1) {
      loadPage()
    }
  }, [s3Bucket, s3Path, filename, pages, pageNumber])

  useEffect(() => {
    if (!loading) {
      scrollAreaRef.current?.querySelector(`mark`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    })
    }
  }, [loading, scrollAreaRef, highlight])

  if (loading) {
    return <Skeleton className="h-10" />
  } else {
    return <StyledMarkdown highlight={highlight}>{markdownContent}</StyledMarkdown>
  }
}

function DocumentViewer({ s3Bucket, s3Path, filename, references, initialReferenceId }: {
  s3Bucket: Document['s3_bucket'],
  s3Path: Document['s3_path'],
  filename: Document['filename'],
  references?: DocumentSource['references']
  initialReferenceId?: number
}) {
  const [pages, setPages] = useState<string[]>([])
  const [pageNumber, setPageNumber] = useState<number>(1)
  const [referenceId, setReferenceId] = useState<number>()
  const scrollAreaRef = useRef<HTMLDivElement>(null)

  // TODO: maybe move highlight find here instead of in line MarkdownRenderer
  const onReferenceChange = (value: number) => {
    setReferenceId(value)
    const reference = references?.find(r => r.reference_id === value)
    if (reference) {
      setPageNumber(pages.findIndex(p => p === reference.s3_page) + 1)
    }
  }

  const onPageNumberChange = (value: number) => {
    setReferenceId(undefined)
    setPageNumber(value)
  }

  useEffect(() => {
    setPageNumber(1)
    setReferenceId(undefined)
  }, [filename])

  // Phase 27.B+C.2: pre-select the reference the user clicked on the
  // chat-message citation badge. We can only resolve the page once
  // `pages` has loaded (the indexOf below depends on it), so this
  // effect waits for both inputs.
  useEffect(() => {
    if (initialReferenceId === undefined || pages.length === 0) return
    const reference = references?.find(r => r.reference_id === initialReferenceId)
    if (!reference) return
    setReferenceId(initialReferenceId)
    const idx = pages.findIndex(p => p === reference.s3_page)
    if (idx >= 0) {
      setPageNumber(idx + 1)
    }
  }, [initialReferenceId, pages, references])

  return (
    <div className="flex flex-col items-center overflow-hidden space-y-4">
      <ScrollArea className="w-full h-full border rounded-md">
        <div ref={scrollAreaRef} className="p-4 grid grid-cols-1">
          <MarkdownRenderer s3Bucket={s3Bucket} s3Path={s3Path} filename={filename} pages={pages} setPages={setPages} pageNumber={pageNumber} highlight={references?.find(r => r.reference_id === referenceId)?.reference_index} scrollAreaRef={scrollAreaRef}/>
        </div>
        <ScrollBar orientation="vertical" />
      </ScrollArea>
      {pages.length > 1 && (
        <div className="flex items-center space-x-2">
          <Button variant="outline" size="icon" disabled={pageNumber <= 1} onClick={() => onPageNumberChange(1)}>
            <ChevronsLeft className="h-4 w-4"/>
          </Button>
          <Button variant="outline" size="icon" disabled={pageNumber <= 1} onClick={() => onPageNumberChange(pageNumber - 1)}>
            <ChevronLeft className="h-4 w-4"/>
          </Button>
          <p className="px-2"><Trans>Page {pageNumber} of {pages.length}</Trans></p>
          <Button variant="outline" size="icon" disabled={pageNumber >= pages.length} onClick={() => onPageNumberChange(pageNumber + 1)}>
            <ChevronRight className="h-4 w-4"/>
          </Button>
          <Button variant="outline" size="icon" disabled={pageNumber >= pages.length} onClick={() => onPageNumberChange(pages.length)}>
            <ChevronsRight className="h-4 w-4"/>
          </Button>
        </div>
      )}
      {references && (
        <ScrollArea className="flex-none w-full h-16 pb-4">
          <ToggleGroup
            type="single"
            variant="outline"
            className="mt-2"
            value={referenceId?.toString() ?? ""}
            onValueChange={(value) => onReferenceChange(Number(value))}
          >
            {references.map(reference => (
              <ToggleGroupItem key={reference.reference_id} value={reference.reference_id.toString()}>
                {reference.reference_id}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>
      )}
    </div>
  )
}
export default DocumentViewer