import { Chat, ChatWithMessages, Invoke } from "@/lib/types/Chat"
import { AssistantMessage, Message, UserMessage } from "@/lib/types/Message"
import RequestError from "@/lib/types/RequestError";

async function chatCompletion(
  chatId: string,
  action: "regenerate" | "expand" | "chat",
  userMessage: UserMessage,
  // Phase 51.B — `DeepResearch` is the canonical name (was `AllForOne`).
  // The alias stays in the union for one phase of soft-deprecation.
  // Phase 59.C — `General` is the new default (user-scoped orchestrator).
  workflow: "ExampleQuestions" | "FocusMode" | "UserSupport" | "QA" | "Report" | "DeepResearch" | "AllForOne" | "AdminAssistant" | "General",
  doc_search: boolean,
  web_search: boolean,
  internal_knowledge: boolean,
  checkpoint: number | null,
  pageNumbers: string[],
  chunkNumbers: number[],
  assistantAnswer: AssistantMessage | null,
  chatName: string | null,
  socketId: string | undefined,
): Promise<Invoke> {
  const locale = localStorage.getItem('vite-ui-locale') ?? import.meta.env.VITE_LOCALE

  await new Promise(res => setTimeout(res, 5000))
  const response = await fetch(`/api/general/v0/chats/${chatId}/invoke` , {
    method: "POST",
    credentials: 'same-origin',
    body: JSON.stringify({
      invoke: action,
      selected_language: locale,
      provider: userMessage.provider,
      llm_model: userMessage.llm_model,
      workflow: workflow,
      user_question: userMessage.content,
      doc_search: doc_search,
      web_search: web_search,
      internal_knowledge: internal_knowledge,
      checkpoint: checkpoint,
      selected_documents: userMessage.documents,
      selected_page_numbers: pageNumbers,
      selected_chunk_numbers: chunkNumbers,
      assistant_answer: assistantAnswer,
      chat_name: chatName,
      socket_id: socketId
    }),
    headers: {
      'Content-Type': "application/json; charset=UTF-8",
    },
  })

  const valueResponse = await response.json()
  
  if (!response.ok) {
    return {
      answer: valueResponse.error.message,
      sources: [],
      recorded_notes: {},
      metadata: {
        input_tokens: 0,
        output_tokens: 0,
        llm_model: "None",
      }
    }
  }

  return valueResponse
}

async function newChat(chat_name: string | null) {
  // In the API call, create a new DB entry with user, chat_name, chat_id. Leave empty the messages  
  const response = await fetch('/api/general/v0/chats', {
    method: 'POST',
    credentials: 'same-origin',
    body: JSON.stringify({chat_name}),
    headers: {
      'Content-Type': "application/json; charset=UTF-8",      
    },
  })

  return response
}

async function getChats() {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 2000)

  const response = await fetch('/api/general/v0/chats', {
    method: 'GET',
    credentials: 'same-origin',
    headers: {
      'Content-Type': "application/json; charset=UTF-8",
    },
    signal: controller.signal
  })
  clearTimeout(timeoutId)

  if (!response.ok) {
    throw new RequestError(response.status, response.statusText)
  }

  const value_response = await response.json() as Chat[]
  return value_response
}

async function getChatWithMessages(chatId: string) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 2000)

  const response = await fetch('/api/general/v0/chats/' + chatId, {
    method: 'GET',
    credentials: 'same-origin',
    headers: {
      'Content-Type': "application/json; charset=UTF-8",
    },
  })
  clearTimeout(timeoutId)

  if (!response.ok) {
    throw new RequestError(response.status, response.statusText)
  }

  const value_response = await response.json()

  return value_response as ChatWithMessages
}

async function saveChatWithMessages(chatName: string | null, chatId: string, conversation: Message[]) {
  const payload = {"chat_name": chatName, "conversation": conversation}
  const response = fetch('/api/general/v0/chats/' + chatId, {
    method: 'PATCH',
    credentials: 'same-origin',
    body: JSON.stringify(payload),
    headers: {
      'Content-Type': "application/json; charset=UTF-8",
    },
  })

  return response
}

async function deleteChat(chat: Chat) {
  const response = fetch('/api/general/v0/chats/' + chat.id, {
    credentials: 'same-origin',
    method: 'DELETE',
  })

  return response
}

async function chatFeedback(chatId: string, feedBack: {
  useful_answers: boolean,
  understandable_answers: boolean,
  relevant_sources: boolean,
  other_comments: string,
  message_index: number,
  conversation: Message[]
}) {
  const payload = {"feedback":feedBack}
  const response = fetch(`/api/general/v0/chats/${chatId}/feedback`, {
    method: 'POST',
    credentials: 'same-origin',
    body: JSON.stringify(payload),
    headers: {
      'Content-Type': "application/json; charset=UTF-8",
    },
  })
  return response
}

/**
 * Phase 48.A — resolve an in-flight HITL approval from the chat UI.
 *
 * The chip-row's `awaiting_approval` chip renders Approve / Deny
 * inline action buttons that call this helper with `confirmed: true`
 * (Approve) or `false` (Deny). The backend's `ApprovalManager` signals
 * the paused engine, which then either runs the underlying tool or
 * raises `HITLDenied`. The chip then collapses to a `complete` /
 * `error` frame emitted by the backend's `emit_hitl_resolved`.
 *
 * Backend route: `POST /api/general/v0/chats/{chatId}/approvals/{taskId}`.
 * Body: `{confirmed: boolean, justification: string | null}`.
 * Returns: 200 `{resolved: true}` on success; 409 if already resolved;
 * 404 if the task isn't pending for this chat.
 */
async function resolveApproval(
  chatId: string,
  taskId: string,
  confirmed: boolean,
  justification?: string | null,
): Promise<{ resolved: boolean; status: number }> {
  const response = await fetch(
    `/api/general/v0/chats/${chatId}/approvals/${taskId}`,
    {
      method: 'POST',
      credentials: 'same-origin',
      body: JSON.stringify({ confirmed, justification: justification ?? null }),
      headers: { 'Content-Type': 'application/json; charset=UTF-8' },
    },
  )
  const ok = response.ok
  return { resolved: ok, status: response.status }
}

export default chatCompletion
export { newChat, getChats, getChatWithMessages, saveChatWithMessages, deleteChat, chatFeedback, resolveApproval }