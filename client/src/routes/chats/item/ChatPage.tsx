import chatCompletion, { getChatWithMessages, saveChatWithMessages } from "@/api/chat";
import { Skeleton } from "@/components/ui/skeleton";
import { ChatWithMessages, DocumentSource, Source } from "@/lib/types/Chat";
import { AgentActionFrame, isAgentActionFrame } from "@/lib/types/AgentAction";
import { Route } from "@/lib/types/Route";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Await, defer, useAsyncError, useLoaderData, useOutletContext, useRevalidator } from "react-router-dom";
import { AssistantMessage, DEFAULT_WORKFLOW, Message, MessageRole, UserMessage, Workflow, workflowToMode } from "@/lib/types/Message";
import { ScrollArea } from "@/components/ui/scroll-area";
import Repeat from "@/components/ui/custom/repeat";
import AgentActionRow from "@/components/sections/AgentActionRow";
import ChatDocuments from "@/components/sections/ChatDocuments";
import ChatMessages, { AssistantMessageComponent, UserMessageComponent } from "@/components/sections/ChatMessages";
import ChatHeader from "@/components/sections/ChatHeader";
import ChatTextbox from "@/components/sections/ChatTextbox";
import useSocket from "@/lib/hooks/useSocket";
import { Document } from "@/lib/types/Document";
import { getDocuments } from "@/api/document";
import { t } from "@lingui/core/macro";
import { Model } from "@/lib/types/Model";
import { getModels } from "@/api/model";
import { AlertDialog, AlertDialogAction, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"
import useAuth from "@/lib/hooks/useAuth";
import { usePreferences } from "@/lib/hooks/usePreferences";
import { Trans } from "@lingui/react/macro";

function ChatPage() {
  const { user } = useAuth()
  const { prefs, loaded: prefsLoaded } = usePreferences()
  const { openDocuments, setOpenDocuments } = useOutletContext() as { openDocuments: boolean, setOpenDocuments: (value: boolean) => void }
  const [models, setModels] = useState<Model[]>([])
  const socket = useSocket()
  // Phase 44 round-4 (EW-44.16) — drive the sidebar refresh
  // after the chat-name BG task lands; same logic as AskPage.
  const revalidator = useRevalidator()

  const [message, setMessage] = useState("")
  const [selectedModel, setSelectedModel] = useState<Model>()
  const [workflow, setWorkflow] = useState<Workflow>(DEFAULT_WORKFLOW)
  const prefsAppliedRef = useRef(false)

  // Phase 28.B: once preferences load, swap the initial workflow if
  // the user has a saved default. We only do this once per page
  // mount — subsequent dropdown changes are user input and must not
  // be overwritten by a late-arriving prefs fetch.
  useEffect(() => {
    if (!prefsLoaded || prefsAppliedRef.current) return
    prefsAppliedRef.current = true
    if (prefs.default_workflow) {
      setWorkflow(prefs.default_workflow)
    }
  }, [prefsLoaded, prefs.default_workflow])
  const mode = workflowToMode(workflow)
  const [selectedDocuments, setSelectedDocuments] = useState<Document[]>([])
  const [internalKnowledge, setInternalKnowledge] = useState(true)
  const [docSearch, setDocSearch] = useState(false)
  const [webSearch, setWebSearch] = useState(false)
  const [checkpoint, setCheckpoint] = useState<number>()

  const [tokensBlock, setTokensBlock] = useState(false)
  const dateBlock = useMemo(() => {
      const expiry = new Date(user!.expiring_date_trial)
      const current = new Date()
  
      return expiry <= current
    }, [user])
  
  const [latestAssistantMessage, setLatestAssistantMessage] = useState<string | undefined>()
  const [latestUserMessage, setLatestUserMessage] = useState<string | undefined>()
  // Phase 44 — per-turn agent-action chip frames (UC-23). Append-only;
  // the AgentActionRow collapses correlated start/complete pairs by id.
  // Cleared at the top of `onSend` / `onRegen` / `onExpand` so a new
  // turn starts with an empty row.
  const [agentActions, setAgentActions] = useState<AgentActionFrame[]>([])
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const data = useLoaderData() as unknown as {id: string, chatWithMessages: Promise<ChatWithMessages>, models: Promise<Model[]>}
  const pageChanged = useRef(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [chatName, setChatName] = useState<string | null>(null)
  const [chatId, setChatId] = useState<string>("")
  const [loading, setLoading] = useState<boolean>(false)

  const [openDocument, setOpenDocument] = useState<DocumentSource>()
  const [initialReferenceId, setInitialReferenceId] = useState<number | undefined>()
  
  useEffect(() => {
    pageChanged.current = true
    setMessage("")
    setLoading(false)
    setLatestAssistantMessage(undefined)
    setLatestUserMessage(undefined)

    data.chatWithMessages.then(c => {
      setMessages(c.messages)
      setChatName(c.name)
      setChatId(c.id)
    })
  }, [data.chatWithMessages])

  useEffect(() => {
    data.models.then((models) => {
      setModels(models)
      // Phase 28.B: prefer the user's saved `preferred_model` if it
      // exists, has budget remaining, and matches a registered model.
      // The wire shape is `<provider>/<model>`. Falls back to the
      // first model with budget when no preference is set or the
      // preferred model is over its limit.
      const preferred = prefs.preferred_model
      const candidate = preferred
        ? models.find((m) =>
            `${m.provider}/${m.model}` === preferred &&
            m.tot_tokens_timeframe < m.tokens_limit,
          )
        : undefined
      setSelectedModel(candidate ?? models.find(model => model.tot_tokens_timeframe < model.tokens_limit))

      if (models.every(model => model.tot_tokens_timeframe >= model.tokens_limit) || models.reduce((a, b) => a + b.tot_tokens_timeframe, 0) >= user!.tot_token_limit) {
        setTokensBlock(true)
      }
    })

  }, [user, data.models, prefs.preferred_model])

  useEffect(() => {
    if (chatId !== "") {
      // Phase 44 — the `chat-{id}` channel carries three frame shapes:
      //   1. string chunks (legacy text-delta path).
      //   2. dict envelopes with `type: "agent-action"` (UC-23 chips).
      //   3. the final `ChatResponse` envelope (closing event).
      // We dispatch on shape: action frames feed `agentActions`,
      // strings feed the streaming text bubble, and the closing
      // envelope is handled by `callChatCompletion`'s `.then(...)`.
      socket.on(`chat-${chatId}`, (data) => {
        if (isAgentActionFrame(data)) {
          setAgentActions(prev => [...prev, data])
          return
        }
        if (typeof data === "string") {
          setLatestAssistantMessage(data)
        }
      })

      return () => {
        socket.off(`chat-${chatId}`)
      }
    }

  }, [socket, chatId])

  const callChatCompletion = (
    oldMessages: Message[],
    userMessage: UserMessage,
    assistantAnswer: AssistantMessage | null,
    action: "regenerate" | "expand" | "chat",
    workflow: Workflow,
  ) => {
    pageChanged.current = false
    setLoading(true)
    chatCompletion(
      chatId,
      action,
      userMessage,
      workflow,
      docSearch,
      webSearch,
      internalKnowledge,
      oldMessages.length,
      [],
      [],
      assistantAnswer,
      chatName,
      socket.id
    ).then((res) => {
      if (!pageChanged.current) {
        const updatedMessages: Message[] = [
          ...oldMessages,
          userMessage,
          {
            role: MessageRole.Assistant,
            content: res.answer,
            sources: res.sources,
            recorded_notes: res.recorded_notes,
            metadata: res.metadata
          }
        ]

        setMessages(updatedMessages)
        setLatestAssistantMessage(undefined)
        setLatestUserMessage(undefined)
        // Phase 44 round-3 (EW-44.6) — clear the in-flight chip-row
        // when the closing envelope lands. The chip-row's job is to
        // narrate the agent's work DURING the stream; once the
        // persisted assistant message is on screen with its sources
        // + recorded_notes, the row becomes stale and the user reads
        // it as "still in flight". `metadata.actions` on the
        // persisted message is the durable forensic-replay surface.
        setAgentActions([])
        // Phase 44 round-4 (EW-44.16) — refresh the sidebar's
        // "Recent chats" list 3 s after the closing envelope so a
        // freshly-created chat's backend-assigned name (from the
        // chat-name BG task) replaces the placeholder "New chat".
        setTimeout(() => revalidator.revalidate(), 3000)

        let updatedSelectedModel = selectedModel
        const updatedModels = models.map(model => {
          if (model.model === selectedModel?.model && model.provider === selectedModel.provider) {
            updatedSelectedModel = {
              ...model,
              tot_tokens: model.tot_tokens + res.metadata.input_tokens + res.metadata.output_tokens,
              tot_tokens_timeframe: model.tot_tokens_timeframe + res.metadata.input_tokens + res.metadata.output_tokens
            }

            return updatedSelectedModel
          }

          return model
        })

        setModels(updatedModels)
        if (!(updatedSelectedModel && updatedSelectedModel.tot_tokens_timeframe < updatedSelectedModel.tokens_limit)) {
          setSelectedModel(updatedModels.find(model => model.tot_tokens_timeframe < model.tokens_limit))
        }
        if (updatedModels.every(model => model.tot_tokens_timeframe >= model.tokens_limit) || models.reduce((a, b) => a + b.tot_tokens_timeframe, 0) >= user!.tot_token_limit) {
          setTokensBlock(true)
        }

        saveChatWithMessages(chatName, chatId, updatedMessages)
      }
    }).catch((error) => {
      setLatestAssistantMessage(t`Something went wrong, retry or change question.`)
      console.log("Something went wrong: ", error)
    }).finally(() => {
      setLoading(false)
    })
  }

  const onExpand = async () => {
    const toExpand = messages[messages.length - 1] as AssistantMessage
    const userQuestion = messages[messages.length - 2] as UserMessage
    setLatestUserMessage(userQuestion.content)
    setLatestAssistantMessage("")
    setAgentActions([])

    const oldMessages = messages.slice(0, -2)
    setMessages(oldMessages)
    callChatCompletion(oldMessages, userQuestion, toExpand, "expand", "QA")
  }

  const onRegen = async () => {
    const toRegen = messages[messages.length - 1] as AssistantMessage
    const userQuestion = messages[messages.length - 2] as UserMessage
    setLatestUserMessage(userQuestion.content)
    setLatestAssistantMessage("")
    setAgentActions([])

    const oldMessages = messages.slice(0, -2)
    setMessages(oldMessages)
    callChatCompletion(oldMessages, userQuestion, toRegen, "regenerate", "QA")
  }

  const onEdit = (messageIndex: number) => {
    const toEdit = messages[messageIndex] as UserMessage
    setMessage(toEdit.content)

    setCheckpoint(messageIndex)
  }

  const onSend = async () => {
    const userQuestion = message
    setLatestUserMessage(userQuestion)
    setLatestAssistantMessage("")
    setAgentActions([])
    setMessage("")

    const oldMessages = checkpoint !== undefined ? messages.slice(0, checkpoint) : messages
    setMessages(oldMessages)
    setCheckpoint(undefined)

    callChatCompletion(oldMessages, {role: MessageRole.User, llm_model: selectedModel!.model, provider: selectedModel!.provider, mode: mode, content: userQuestion, documents: selectedDocuments}, null, "chat", workflow)
  }

  const onSourceClick = (source: Source, referenceId?: number) => {
    if (source.type === "docs") {
      setOpenDocuments(true)
      setOpenDocument(source)
      setInitialReferenceId(referenceId)
    }
  }

  return (
    <div className="flex h-full relative">
      <ScrollArea className="w-full h-full relative">
        <div className="flex justify-center pt-4">
          <div className="flex flex-col space-y-4 w-full max-w-[58rem] mx-4">
            <ChatHeader />
            <Suspense
              fallback={(
                <Repeat times={2}>
                  <div className="flex space-x-2">
                    <Skeleton className="rounded-lg ml-auto w-48" />
                    <Skeleton className="w-12 h-12 rounded-full" />
                  </div>
                  <div className="flex space-x-2">
                    <Skeleton className="w-12 h-12 rounded-full" />
                    <Skeleton className="rounded-lg ml-auto w-96" />
                  </div>
                </Repeat>
              )}
            >
              <Await resolve={data.chatWithMessages}>
                {() => <ChatMessages messages={messages} chatId={chatId} bottomRef={bottomRef} loading={loading && latestAssistantMessage === undefined} checkpoint={checkpoint} onEdit={onEdit} onExpand={onExpand} onRegen={onRegen} onSourceClick={onSourceClick}/>}
              </Await>
            </Suspense>
            
            {latestUserMessage !== undefined && <UserMessageComponent messageIndex={messages.length} onEdit={onEdit} message={{role: MessageRole.User, llm_model: selectedModel!.model, provider: selectedModel!.provider, mode: mode, content: latestUserMessage, documents: selectedDocuments}} />}
            {/* Phase 44 / UC-23 — in-flight agent-action chips above the streaming bubble. */}
            {(loading || agentActions.length > 0) && (
              <AgentActionRow
                frames={agentActions}
                loading={loading}
                streamingText={latestAssistantMessage}
                chatId={chatId}
              />
            )}
            {latestAssistantMessage !== undefined && <AssistantMessageComponent text={latestAssistantMessage} loading={loading} />}
            <div className="pt-[18.5rem]" ref={bottomRef} />
          </div>
        </div>
        <ChatTextbox
          disabled={tokensBlock || dateBlock}
          message={message}
          setMessage={setMessage}
          models={models} selectedModel={selectedModel} setSelectedModel={setSelectedModel}
          workflow={workflow} setWorkflow={setWorkflow}
          selectedDocuments={selectedDocuments} setSelectedDocuments={setSelectedDocuments}
          internalKnowledge={internalKnowledge} setInternalKnowledge={setInternalKnowledge}
          docSearch={docSearch} setDocSearch={setDocSearch}
          webSearch={webSearch} setWebSearch={setWebSearch}
          loading={loading}
          checkpoint={checkpoint} setCheckpoint={setCheckpoint}
          onSend={onSend}
        />
      </ScrollArea>
      {openDocuments && <ChatDocuments messages={messages} openDocument={openDocument} setOpenDocument={setOpenDocument} initialReferenceId={initialReferenceId}/>}
      {tokensBlock && (
        <AlertDialog defaultOpen>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                <Trans>You have run out of tokens!</Trans>
              </AlertDialogTitle>
              <AlertDialogDescription>
                <Trans>
                  <div>Please wait for the reset period or ask an administrator to increase your tokens allocation, until then you won't be able to sent more messages.</div>
                  <div className="mt-2">You can find more informations about tokens consumption in the "Tokens Consumption" section of your settings.</div>
                </Trans>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogAction>
                <Trans>Continue</Trans>
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
      {dateBlock && (
        <AlertDialog defaultOpen>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                <Trans>You have run out of time!</Trans>
              </AlertDialogTitle>
              <AlertDialogDescription>
                <Trans>
                  <div>Please ask an administration to update your expiration date, until then you won't be able to sent more messages.</div>
                  <div className="mt-2">You can find more information about your account expiration date in the "User Data" section of your settings.</div>
                </Trans>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogAction>
                <Trans>Continue</Trans>
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  )
}

function ChatNameError() {
  const error = useAsyncError() as Error
  return (
    <span className="text-destructive">
      {error.message}
    </span>
  )
}

const ChatRoute: Route = {
  path: ":chatId",
  element: <ChatPage />,
  loader: async ({ params }) => {
    if (!params.chatId) {
      throw Error("Chat id required")
    }

    const chatId = params.chatId
    const chatWithMessages = getChatWithMessages(chatId)
    const documents = getDocuments()
    const models = getModels()

    return defer({ id: params.chatId, chatWithMessages, documents, models })
  },
  handle: {
    getPageName: (data) => {
      const chatReq = (data as { id: string, chatWithMessages: Promise<ChatWithMessages> }).chatWithMessages
      return (
        <Suspense
          fallback={(<Skeleton className="rounded-md h-4 w-12" />)}
        >
          <Await resolve={chatReq} errorElement={<ChatNameError />}>
            {(chat: ChatWithMessages) => chat.name}
          </Await>
        </Suspense>
      )
    }
  }
}

export default ChatRoute