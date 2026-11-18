
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { Button } from "../ui/button";
import { MutableRefObject, useEffect } from "react";
import { Card } from "../ui/card";
import { AssistantMessage, Message, UserMessage } from "@/lib/types/Message";
import type { DocumentSource, WebSource } from "@/lib/types/Chat";
import ChatFeedbackDialog from "./ChatFeedbackDialog";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { CircleHelp, Copy, FileText, Globe, LoaderCircle, Notebook, Pencil, Redo, UnfoldVertical, User } from "lucide-react";
import { StyledMarkdown } from "../ui/custom/styled-markdown";
import MessageInfoDialog from "./MessageInfoDialog";
import { PersistentTraceBlock } from "./PersistentTraceBlock";
import { Trans } from "@lingui/react/macro";
import { toast } from "sonner";
import { t } from "@lingui/core/macro";
import copy from "copy-to-clipboard";
import { Source } from "@/lib/types/Chat";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

function UserMessageComponent({ messageIndex, message, onEdit }: { messageIndex: number, message: UserMessage, onEdit: (messageIndex: number) => void }) {
  return (
    <div className="w-full flex space-x-2">
      <div className="max-w-full ml-auto flex flex-col  space-y-1">
        <Card
          className="px-3 py-2 text-sm bg-primary text-primary-foreground whitespace-pre-wrap"
          style={{ overflowWrap: "anywhere" }}
        >
          {message.content}
        </Card>
        <div className="text-sm text-muted-foreground flex space-x-2 items-center">
          <Button variant={"ghost"} size={"sm"} onClick={() => {
            copy(message.content)
            toast.info(t`Message copied to clipboard`)
          }}>
            <Copy className="w-4 h-4 mr-0 sm:mr-2" /> <span className="hidden sm:contents"><Trans>Copy</Trans></span>
          </Button>
          <Separator orientation="vertical" className="h-4" />
          <Button variant={"ghost"} size={"sm"} onClick={() => onEdit(messageIndex)}>
            <Pencil className="w-4 h-4 mr-0 sm:mr-2" /> <span className="hidden sm:contents"><Trans>Edit</Trans></span>
          </Button>
        </div>
      </div>
      <Avatar className="bg-background">
        <AvatarImage src="" alt="@you"/>
        <AvatarFallback>
          <User className="h-5 w-5"/>
        </AvatarFallback>
      </Avatar>
    </div>
  )
}

function AssistantMessageComponent(props: {
  messageIndex: number,
  chatId: string,
  fullChat: Message[],
  loading: boolean,
  checkpoint: number | undefined
  onExpand: () => void,
  onRegen: (messageIndex: number) => Promise<void>,
  onSourceClick: (source: Source, referenceId?: number) => void
} | {
  text: string,
  loading: boolean,
}) {
  const renderMessage = () => {
    if (props.loading) {
      if ("text" in props && props.text.length > 0) {
        <div className="w-full h-full min-h-7 flex flex-col space-y-4 text-muted-foreground">
          <StyledMarkdown>{props.text ?? ""}</StyledMarkdown>
        </div>
      } else {
        return (
          <LoaderCircle className="w-5 h-5 my-1 animate-spin"/>
        )
      }
    }

    if ("text" in props) {
      return (
        <div className="w-full h-full min-h-7 flex flex-col space-y-4 text-muted-foreground">
          <StyledMarkdown>{props.text}</StyledMarkdown>
        </div>
      )
    } else {
      const message = props.fullChat[props.messageIndex] as AssistantMessage
      // Phase 55.E: typed narrowing via predicates so `endpoint_name`
      // on `DocumentSource.references[].endpoint_name` is reachable
      // without a cast in the JSX below.
      const doucumentSources = message.sources?.filter(
        (source): source is DocumentSource => source.type === "docs"
      )
      const webSources = message.sources?.filter(
        (source): source is WebSource => source.type === "web"
      )
      // Phase 28.C: flatten every source's references into a single
      // {reference_id, text} list so StyledMarkdown can resolve inline
      // `[N]` markers in the assistant body to per-chunk hover previews.
      const inlineCitations = (message.sources ?? []).flatMap(s =>
        s.references.map(ref => ({
          reference_id: ref.reference_id,
          text: ref.text ?? null,
          s3_page: 's3_page' in ref ? ref.s3_page : null,
          chunk_number: ref.chunk_number,
        }))
      )
      return (
        <div className="w-full h-full min-h-7 flex flex-col space-y-4 hyphens-manual">
          <StyledMarkdown references={inlineCitations}>
            {message.content}
          </StyledMarkdown>
          {doucumentSources && doucumentSources.length > 0 && (
            <div className="mt-2 flex flex-row items-center flex-wrap gap-2 border rounded-md p-2">
              <div className="text-muted-foreground inline-flex items-center gap-1 text-xs">
                <FileText className="size-3"/>
                <Trans>Document sources:</Trans>
              </div>
              <TooltipProvider delayDuration={200}>
                {doucumentSources.flatMap(s =>
                  s.references.map(ref => (
                    <Tooltip key={`${s.filename}-${ref.reference_id}`}>
                      <TooltipTrigger asChild>
                        {/* Phase 55.E: badge surfaces the knowledge
                            endpoint name when the backend supplied it
                            (Phase 54.F wire-contract field). Renders
                            as a subtle "from <endpoint>" trailer so
                            the existing badge layout doesn't break
                            for legacy chunks (where endpoint_name is
                            null and the trailer is hidden). */}
                        <Badge
                          variant="secondary"
                          className="cursor-pointer"
                          onClick={() => props.onSourceClick(s, ref.reference_id)}
                          data-endpoint={ref.endpoint_name ?? undefined}
                        >
                          {s.filename} [{ref.reference_id}]
                          {ref.endpoint_name ? (
                            <span className="ml-1 text-[10px] opacity-70">
                              · {ref.endpoint_name}
                            </span>
                          ) : null}
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs">
                        {ref.endpoint_name ? (
                          <Trans>
                            From {ref.endpoint_name} — page {ref.s3_page} · chunk {ref.chunk_number} — click to jump
                          </Trans>
                        ) : (
                          <Trans>
                            Page {ref.s3_page} · chunk {ref.chunk_number} — click to jump
                          </Trans>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  ))
                )}
              </TooltipProvider>
            </div>
          )}
          {webSources && webSources.length > 0 && (
            <div className="mt-2 flex flex-row flex-wrap gap-2 border rounded-md p-2">
              <div className="text-muted-foreground inline-flex items-center gap-1 text-xs">
                <Globe className="size-3"/>
                <Trans>Web sources:</Trans>
              </div>
              <TooltipProvider delayDuration={200}>
                {webSources.flatMap(s =>
                  s.references.map(ref => (
                    <Tooltip key={`${s.filename}-${ref.reference_id}`}>
                      <TooltipTrigger asChild>
                        {/* `ref.uri` is typed `string | null` (per WebSource);
                            <a href> accepts `string | undefined`. Coalesce
                            null → undefined so TS strict mode is happy. */}
                        <a href={ref.uri ?? undefined} target="_blank" rel="noreferrer">
                          <Badge variant="secondary" className="cursor-pointer">
                            {s.filename} [{ref.reference_id}]
                          </Badge>
                        </a>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs max-w-md break-all">
                        <Trans>Open external page: {ref.uri}</Trans>
                      </TooltipContent>
                    </Tooltip>
                  ))
                )}
              </TooltipProvider>
            </div>
          )}
        </div>
      )
    }
  }
  
  return (
    <>
      <div className="w-full flex space-x-2">
        <Avatar className="p-1 bg-background">
          <AvatarImage src={"/icon.svg"} alt="@assistant"/>
          <AvatarFallback>CA</AvatarFallback>
        </Avatar>
        <div className="max-w-full mr-auto flex flex-col space-y-1">
          <Card
            className="px-3 py-2 text-sm"
            style={{ overflowWrap: "anywhere" }}
          >
            {renderMessage()}
          </Card>
          {/* Phase 45.D — persistent collapsible trace block. The
              ChatMessage `renderMessage` branch above already shows
              the streaming text + citations; this block carries the
              full per-turn agent-action chip history rehydrated from
              metadata.actions so an operator can replay a past turn
              without re-streaming. Renders only on full assistant
              messages (not the in-flight streaming placeholder). */}
          {!("text" in props) && (() => {
            const msg = props.fullChat[props.messageIndex] as AssistantMessage
            const actions = msg.metadata?.actions ?? []
            if (actions.length === 0) return null
            return (
              <PersistentTraceBlock
                frames={actions}
                tokensIn={msg.metadata?.input_tokens ?? 0}
                tokensOut={msg.metadata?.output_tokens ?? 0}
              />
            )
          })()}
          {!("text" in props) && (
            <>
              <div className="text-sm text-muted-foreground flex space-x-2 items-center">
                <MessageInfoDialog userMessage={props.fullChat[props.messageIndex - 1] as UserMessage} assistantMessage={props.fullChat[props.messageIndex] as AssistantMessage}>
                  <Button variant={"ghost"} size={"sm"} disabled={props.loading}>
                    <CircleHelp className="w-4 h-4 mr-0 sm:mr-2" /> <span className="hidden sm:contents"><Trans>Information</Trans></span>
                  </Button>
                </MessageInfoDialog>
                <Separator orientation="vertical" className="h-4" />
                <ChatFeedbackDialog messageIndex={props.messageIndex} chatId={props.chatId} fullChat={props.fullChat}>
                  <Button variant="ghost" size={"sm"} disabled={props.loading}>
                    <Notebook className="w-4 h-4 mr-0 sm:mr-2"/> <span className="hidden sm:contents"><Trans>Feedback</Trans></span>
                  </Button>
                </ChatFeedbackDialog>
                <Separator orientation="vertical" className="h-4" />
                <Button variant={"ghost"} size={"sm"} onClick={() => {
                  copy(props.fullChat[props.messageIndex].content)
                  toast.info(t`Message copied to clipboard`)
                }}>
                  <Copy className="w-4 h-4 mr-0 sm:mr-2" /> <span className="hidden sm:contents"><Trans>Copy</Trans></span>
                </Button>
                {props.messageIndex === (props.fullChat.length - 1) && (
                  <>
                    <Separator orientation="vertical" className="h-4" />
                    <Button variant="ghost" size={"sm"} disabled={props.loading || props.checkpoint !== undefined} onClick={props.onExpand}>
                      <UnfoldVertical className="w-4 h-4 mr-0 sm:mr-2"/> <span className="hidden sm:contents"><Trans>Expand</Trans></span>
                    </Button>
                    <Separator orientation="vertical" className="h-4" />
                    <Button variant="ghost" size={"sm"} disabled={props.loading || props.checkpoint !== undefined} onClick={() => props.onRegen(props.messageIndex)}>
                      <Redo className="w-4 h-4 mr-0 sm:mr-2"/> <span className="hidden sm:contents"><Trans>Regenerate</Trans></span>
                    </Button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>

  )
}

function ChatMessages({messages, chatId, bottomRef, loading, checkpoint, onEdit, onExpand, onRegen, onSourceClick}: {
  messages: Message[],
  chatId: string,
  bottomRef: MutableRefObject<HTMLDivElement | null>,
  loading: boolean
  checkpoint: number | undefined
  onEdit: (messageIndex: number) => void
  onExpand: () => Promise<void>
  onRegen: (messageIndex: number) => Promise<void>
  onSourceClick: (source: Source, referenceId?: number) => void
}) {
  useEffect(() => {
    bottomRef.current?.scrollIntoView({behavior: 'smooth', block: 'end', inline: 'center'})
  })

  return (
    <>
      {messages?.map((message, index) => {
        if (message.role === "assistant") return <AssistantMessageComponent key={"message " + index} chatId={chatId} messageIndex={index} fullChat={messages} loading={loading && index === (messages.length - 1)} checkpoint={checkpoint} onExpand={onExpand} onRegen={onRegen} onSourceClick={onSourceClick}/>
        if (message.role === "user") return <UserMessageComponent key={"message " + index} message={message} messageIndex={index} onEdit={onEdit} />
        return <></>
      })}
    </>
  )
}

export default ChatMessages
export {UserMessageComponent, AssistantMessageComponent}