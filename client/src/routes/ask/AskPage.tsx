import chatCompletion, { newChat, saveChatWithMessages } from "@/api/chat"
import { getDocuments } from "@/api/document"
import AgentActionRow from "@/components/sections/AgentActionRow"
import ChatDocuments from "@/components/sections/ChatDocuments"
import ChatHeader from "@/components/sections/ChatHeader"
import ChatMessages, { AssistantMessageComponent, UserMessageComponent } from "@/components/sections/ChatMessages"
import ChatTextbox from "@/components/sections/ChatTextbox"
import { AgentActionFrame, isAgentActionFrame } from "@/lib/types/AgentAction"
import Navigation from "@/components/ui/custom/navigation"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Toggle } from "@/components/ui/toggle"
import useSocket from "@/lib/hooks/useSocket"
import { Document } from "@/lib/types/Document"
import { AssistantMessage, DEFAULT_WORKFLOW, Message, MessageRole, UserMessage, Workflow, workflowToMode } from "@/lib/types/Message"
import { Route } from "@/lib/types/Route"
import { Book, BotMessageSquare, MessagesSquare } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { Await, defer, NavLink, useLoaderData, useRevalidator, useSearchParams } from "react-router-dom"
import { getChats } from "@/api/chat"
import { Chat, DocumentSource, Source } from "@/lib/types/Chat"
import { SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarMenuSkeleton } from "@/components/ui/sidebar"
import { Suspense } from "react"
import AsyncErrorAlert from "@/components/ui/custom/async-error-alert"
import { Alert } from "@/components/ui/alert"
import Repeat from "@/components/ui/custom/repeat"
import { Trans } from "@lingui/react/macro"
import { t } from "@lingui/core/macro"
import { getModels } from "@/api/model"
import { Model } from "@/lib/types/Model"
import { AlertDialog, AlertDialogAction, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"
import useAuth from "@/lib/hooks/useAuth"
import { usePreferences } from "@/lib/hooks/usePreferences"

function AskPage() {
  const { user } = useAuth()
  const { prefs, loaded: prefsLoaded } = usePreferences()
  const data = useLoaderData() as unknown as { models: Promise<Model[]> }
  // Phase 44 round-4 (EW-44.16) — drive the chats-list sidebar
  // refresh after a new chat lands a real auto-generated name.
  // The chat-name BG task runs ~1-3 s AFTER the chat-invoke
  // response returns, so the immediate `.then(...)` revalidation
  // would still see the literal "New chat" placeholder; schedule
  // a single delayed revalidation 3 s after the closing envelope.
  const revalidator = useRevalidator()

  const [openDocuments, setOpenDocuments] = useState(false)
  const [models, setModels] = useState<Model[]>([])
  const socket = useSocket()

  const [message, setMessage] = useState("")
  const [selectedModel, setSelectedModel] = useState<Model>()
  const [workflow, setWorkflow] = useState<Workflow>(DEFAULT_WORKFLOW)
  const prefsAppliedRef = useRef(false)

  // Phase 28.B: apply saved default_workflow once prefs load.
  useEffect(() => {
    if (!prefsLoaded || prefsAppliedRef.current) return
    prefsAppliedRef.current = true
    if (prefs.default_workflow) {
      setWorkflow(prefs.default_workflow)
    }
  }, [prefsLoaded, prefs.default_workflow])

  // Phase 59.G — Apps sidebar tiles navigate here with `?app={workflow}`;
  // pick it up + set the workflow state once on mount. Cleared from the
  // URL after read so a refresh doesn't re-pin the workflow on the next
  // mount.
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const appWorkflow = searchParams.get("app")
    if (appWorkflow) {
      setWorkflow(appWorkflow as Workflow)
      setSearchParams((sp) => {
        sp.delete("app")
        return sp
      }, { replace: true })
    }
  }, [searchParams, setSearchParams])
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
  // Phase 44 / UC-23 — in-flight agent-action chip frames. Same pattern
  // as `ChatPage.tsx`: the chat-{id} listener dispatches by payload
  // shape; this list is cleared at the top of every turn.
  const [agentActions, setAgentActions] = useState<AgentActionFrame[]>([])
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const [messages, setMessages] = useState<Message[]>([])
  const [chat, setChat] = useState<Chat | undefined>(undefined)
  const [loading, setLoading] = useState<boolean>(false)

  const [openDocument, setOpenDocument] = useState<DocumentSource>()
  const [initialReferenceId, setInitialReferenceId] = useState<number | undefined>()

  useEffect(() => {
    data.models.then((models) => {
      setModels(models)
      // Phase 28.B: prefer the user's saved `preferred_model` if it
      // exists, has budget remaining, and matches a registered model.
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
    if (chat?.id) {
      // Phase 44 — dispatch by payload shape. Action frames feed the
      // chip row; strings feed the streaming text bubble; the closing
      // envelope is handled by `callChatCompletion`'s `.then(...)`.
      socket.on(`chat-${chat.id}`, (data) => {
        if (isAgentActionFrame(data)) {
          setAgentActions(prev => [...prev, data])
          return
        }
        if (typeof data === "string") {
          setLatestAssistantMessage(data)
        }
      })

      return () => {
        socket.off(`chat-${chat.id}`)
      }
    }

  }, [socket, chat])

  const callChatCompletion = async (
    oldMessages: Message[],
    userMessage: UserMessage,
    assistantAnswer: AssistantMessage | null,
    action: "regenerate" | "expand" | "chat",
    workflow: Workflow,
  ) => {
    let tmpChat = chat
    setLoading(true)

    if (tmpChat === undefined) {
      const req = await newChat(null)
      if (req.ok) {
        tmpChat = await req.json()
        setChat(tmpChat)
      }
    }

    if (tmpChat) {
      chatCompletion(
        tmpChat.id,
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
        tmpChat.name,
        socket.id,
      ).then((res) => {
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
        // when the closing envelope lands (same logic as
        // `ChatPage.tsx`). `metadata.actions` on the persisted
        // message is the durable forensic-replay surface.
        setAgentActions([])
        // Phase 44 round-4 (EW-44.16) — refresh the sidebar's
        // "Recent chats" list so a freshly-created chat's
        // backend-assigned name (from the chat-name BG task)
        // replaces the placeholder "New chat" in the React
        // sidebar. 3 s gives the BG task time to write; the
        // revalidator skips if it's already in flight.
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

        if (tmpChat.name === null && res.metadata.chat_name) {
          saveChatWithMessages(res.metadata.chat_name, tmpChat.id, updatedMessages)
          setChat({...tmpChat, name: res.metadata.chat_name})
        } else {
          saveChatWithMessages(tmpChat.name, tmpChat.id, updatedMessages)
        }
      }).catch((error) => {
        setLatestAssistantMessage(t`Something went wrong, retry or change question.`)
        console.log("Something went wrong: ", error)
      }).finally(() => {
        setLoading(false)
      })
    }
  }

  const onExpand = async () => {
    const toExpand = messages[messages.length - 1] as AssistantMessage
    const userQuestion = messages[messages.length - 2] as UserMessage
    setLatestUserMessage(userQuestion.content)
    setLatestAssistantMessage(toExpand.content)
    setAgentActions([])

    const oldMessages = messages.slice(0, -2)
    setMessages(oldMessages)
    callChatCompletion(oldMessages, userQuestion, toExpand, "expand", "QA")
  }

  const onRegen = async () => {
    const toRegen = messages[messages.length - 1] as AssistantMessage
    const userQuestion = messages[messages.length - 2] as UserMessage
    setLatestUserMessage(userQuestion.content)
    setLatestAssistantMessage(toRegen.content)
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

    await callChatCompletion(oldMessages, {role: MessageRole.User, llm_model: selectedModel!.model, provider: selectedModel!.provider, mode: mode, content: userQuestion, documents: selectedDocuments}, null, "chat", workflow)
  }

  const onSourceClick = (source: Source, referenceId?: number) => {
    if (source.type === "docs") {
      setOpenDocuments(true)
      setOpenDocument(source)
      setInitialReferenceId(referenceId)
    }
  }

  return (
    <div className="w-full flex flex-col h-screen">
      <Navigation>
        <Toggle onClick={() => setOpenDocuments(!openDocuments)} variant="outline" pressed={openDocuments}>
          <Book className="h-4 w-4 mr-0 md:mr-2" /> <span className="hidden md:block"><Trans>Documents list</Trans></span>
        </Toggle>
      </Navigation>
      <main className="h-full overflow-hidden">
        <div className="flex h-full relative">
          <ScrollArea className="w-full h-full relative">
            <div className="flex justify-center pt-4">
              <div className="flex flex-col space-y-4 w-full max-w-[58rem] mx-4">
                <ChatHeader/>
                {chat && <ChatMessages messages={messages} chatId={chat.id} bottomRef={bottomRef} loading={loading && latestAssistantMessage === undefined} checkpoint={checkpoint} onEdit={onEdit} onExpand={onExpand} onRegen={onRegen} onSourceClick={onSourceClick}/>}
                {latestUserMessage !== undefined && <UserMessageComponent messageIndex={messages.length} onEdit={onEdit} message={{role: MessageRole.User, llm_model: selectedModel!.model, provider: selectedModel!.provider, mode: mode, content: latestUserMessage, documents: selectedDocuments}} />}
                {/* Phase 44 / UC-23 — in-flight agent-action chips above the streaming assistant bubble. */}
                {(loading || agentActions.length > 0) && (
                  <AgentActionRow
                    frames={agentActions}
                    loading={loading}
                    streamingText={latestAssistantMessage}
                    chatId={chat?.id}
                  />
                )}
                {latestAssistantMessage !== undefined && <AssistantMessageComponent text={latestAssistantMessage} loading={loading} onRegen={onRegen}/>}
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
                      <div>Please wait for the reset period or ask to the administration to increase your token allocation, until then you won't be able to sent more messages.</div>
                      <div className="mt-2">You can find more informations about tokens consumtion in the "Tokens Consumption" section of your settings.</div>
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
                      <div>Please ask to the administration to update your expiration date, until then you won't be able to sent more messages.</div>
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
      </main>
    </div>
  )
}

function AskSidebarError({ open }: { open: boolean }) {
  if (open) {
    return (<AsyncErrorAlert />)
  } else {
    return (<Alert variant="destructive">.</Alert>)
  }
}


const AskRoute: Route = {
  path: "ask",
  element: <AskPage />,
  loader: async () => {
    const chatWithMessages = new Promise((res) => res({messages: []}))
    const documents = getDocuments()
    const chats = getChats()
    const models = getModels()

    return defer({ chats, chatWithMessages, documents, models })
  },
  handle: {
    getPageName: () => import.meta.env.VITE_NAME,
    getPageSidebar: () => ({
      group: "workarea",
      icon: <BotMessageSquare className='h-4 w-4'/>
    }),
    getPageActions: (data, open, revalidatorState) => {
      const chats = (data as { chats: Chat[] }).chats

      return (
        <SidebarGroup>
          <SidebarGroupLabel><Trans>Recent chats</Trans></SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <Suspense
                fallback={(
                  <Repeat times={5}>
                    <SidebarMenuSkeleton showIcon />
                  </Repeat>
                )}
              >
                <Await resolve={chats} errorElement={<AskSidebarError open={open} />}>
                  {(chats: Chat[]) => {
                    if (revalidatorState === "loading") {
                      return (
                        <Repeat times={5}>
                          <SidebarMenuSkeleton showIcon />
                        </Repeat>
                      )
                    } else {
                      return (chats.slice(0,5).map((chat, index) => (
                        <SidebarMenuItem key={"quick" + index}>
                          <NavLink to={"/chats/" + chat.id}>
                            {({ isActive }) => (
                              <SidebarMenuButton isActive={isActive}>
                                <MessagesSquare /> <span>{chat.name}</span>
                              </SidebarMenuButton>
                            )}
                          </NavLink>
                        </SidebarMenuItem>
                      )))
                    }
                  }}
                </Await>
              </Suspense>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      )
    }
  }
}

export default AskRoute