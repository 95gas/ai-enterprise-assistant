
import { ChevronsLeft, FileText, SquareArrowOutUpRight } from "lucide-react"
import { Button } from "../ui/button"
import { ScrollArea } from "../ui/scroll-area"
import { Suspense } from "react"
import DocumentViewer from "../ui/custom/document-viewer"
import AsyncErrorAlert from "@/components/ui/custom/async-error-alert"
import { Await, useLoaderData } from "react-router-dom"
import { Skeleton } from "@/components/ui/skeleton"
import Repeat from "@/components/ui/custom/repeat"
import { Message, MessageRole } from "@/lib/types/Message"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Trans } from "@lingui/react/macro"
import { DocumentSource } from "@/lib/types/Chat"

function getDocumentSources(messages: Message[]) {
  const documentsGroup = new Map<string, DocumentSource>()

  for (const message of messages) {
    if (message.role === MessageRole.Assistant && message.sources) {
      for (const source of message.sources) {
        if (source.type === "docs") {
          const filename = source.filename
          const type = source.type
          const references = source.references
          const present = documentsGroup.get(filename)

          if (present) {
            const referencesSet = new Set(present.references.concat(references))
            documentsGroup.set(filename, {filename, type, references: Array.from(referencesSet.values())})
          } else {
            documentsGroup.set(filename, {filename, type , references})
          }
        }
      }
    }
  }

  return Array.from(documentsGroup.values())
}

function DocumentList({ messages, onDocumentClick }: {
  messages: Message[]
  onDocumentClick: (document: DocumentSource) => void
}) {
  // NOTE: chatWithMassages is of type ChageWithMessages but since the component is reused in Ask we are only expecting messges
  const data = useLoaderData() as unknown as { chatWithMessages: Promise<{messages: Message[]}> }

  return (
    <ScrollArea className="h-full">
      <div className="grid gap-2 p-6 pt-0">
        <Suspense
          fallback={(
            <Repeat times={5}>
              <Skeleton className="h-10" />
            </Repeat>
          )}
        >
          <Await resolve={data.chatWithMessages} errorElement={<AsyncErrorAlert />}>
            {() => (
              <>
                {getDocumentSources(messages).map((document, index) => (
                  <div className="flex space-x-2" key={"document" + index}>
                    <DocumentButton document={document} onClick={onDocumentClick} />
                  </div>
                ))}
              </>
            )}
          </Await>
        </Suspense>
      </div>
    </ScrollArea>

  )
}

function DocumentPreview({ document, onClose, initialReferenceId }: {
  document: DocumentSource
  onClose: () => void
  initialReferenceId?: number
}) {
  return (
    <div className="h-full flex flex-col p-6 pt-0 space-y-2">
      <div className="flex space-x-2">
        <Button variant="outline" size="icon" className="flex-none" onClick={onClose}>
          <ChevronsLeft className="h-4 w-4" />
        </Button>
        <DocumentButton document={document} onClick={() => undefined} />
        {document.references[0].uri && (
          <a href={document.references[0].uri} target="_blank">
            <Button variant="outline">
              <SquareArrowOutUpRight className="h-4 w-4" />
              <Trans>Original</Trans>
            </Button>
          </a>
        )}
      </div>
      <DocumentViewer s3Bucket={document.references[0].s3_bucket} s3Path={document.references[0].s3_path} filename={document.filename} references={document.references} initialReferenceId={initialReferenceId}/>
    </div>
  )
}

function DocumentButton({ document, onClick }: {
  document: DocumentSource,
  onClick: (document: DocumentSource) => void
}) {
  return (
    <Button
      variant="outline"
      size="default"
      className="w-full"
      onClick={() => onClick(document)}
    >
      <div className="flex justify-between w-full items-center">
        <FileText className="h-4 w-4 mr-2 flex-none" />
        <div className="w-28 flex-1 truncate text-left">{document.filename} - {document.references.map(r => r.reference_id).join(", ")}</div>
      </div>
    </Button>
  )
}

function ChatDocuments({ messages, openDocument, setOpenDocument, initialReferenceId }: {
  messages: Message[]
  openDocument: DocumentSource | undefined
  setOpenDocument: (value: DocumentSource | undefined) => void
  initialReferenceId?: number
}) {
  return (
    <Card className="w-[calc(100%-2rem)] h-[calc(100%-2rem)] max-w-full m-4 absolute right-0 lg:static lg:max-w-[40rem]">
      <CardHeader>
        <CardTitle><Trans>Documents list</Trans></CardTitle>
        <CardDescription><Trans>List of documents referenced in the conversation</Trans></CardDescription>
      </CardHeader>
      <div className="overflow-hidden">
        {openDocument
          ? (
            <DocumentPreview
              document={openDocument}
              onClose={() => setOpenDocument(undefined)}
              initialReferenceId={initialReferenceId}
            />
          )
          : (
            <DocumentList
              messages={messages}
              onDocumentClick={setOpenDocument}
            />
          )
        }
      </div>
    </Card>
  )
}

export default ChatDocuments
