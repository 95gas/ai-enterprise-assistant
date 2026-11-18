import { Message } from "./Message"

export type Chat = {
  id: string
  name: string | null
}

export type ChatWithMessages = Chat & { messages: Message[] }

export type WebSource = {
  filename: string
  type: "web"
  references: {
    id: string
    reference_id: number
    type: "web"
    reference_index: null
    chunk_number: number
    s3_bucket: null
    s3_path: null
    s3_page: null
    uri: string
    /** Phase 28.C: chunk-text preview for inline `[N]` hover. */
    text?: string | null
  }[]
}

export type DocumentSource = {
  filename: string
  type: "docs"
  references: {
    id: string
    reference_id: number
    type: "docs"
    reference_index: [number, number]
    chunk_number: number
    s3_bucket: string
    s3_path: string
    s3_page: string
    uri: string | null
    /** Phase 28.C: chunk-text preview for inline `[N]` hover. */
    text?: string | null
    /**
     * Phase 55.E: operator-facing name of the knowledge endpoint
     * that produced this citation (e.g. `"sharepoint-hr"`,
     * `"hr-italy-mcp"`). Surfaced as a chip next to the filename
     * so users see *where* an answer came from. Optional: legacy
     * chunks pre-dating the endpoint subsystem leave this `null`
     * and render under the implicit "internal" fallback.
     */
    endpoint_name?: string | null
  }[]
}

export type Source = WebSource | DocumentSource

//TODO: add other invoke data
export type Invoke = {
    answer: string
    sources: Source[]
    recorded_notes: Record<string, string>
    metadata: {
      input_tokens: number
      output_tokens: number
      llm_model: string
      chat_name?: string
    }
  }
