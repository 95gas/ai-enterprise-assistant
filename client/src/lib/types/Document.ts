type FTDocument = {
  type: "document"
  depth: number
  name: string
  childrens: undefined
  original: Document
}

type FTFolder = {
  type: "folder"
  depth: number
  name: string
  childrens: FileTree[]
  original: undefined
}

export type FileTree = FTDocument | FTFolder

/**
 * Per-doc scope inherited from the backend's `knowledge_artifacts.scope`.
 *
 * - `private` — owned by the uploading user (S3 bucket `users`).
 *   Visible only to the owner; the /documents tree groups these
 *   under "My documents".
 * - `public` — shared org-wide (S3 bucket `shared`) with optional
 *   visibility-group ACL on top. Grouped under "Common documents"
 *   in the tree.
 * - `external` — pulled from a registered external connector
 *   (SharePoint / Wiki / Mock). Grouped under "External sources"
 *   so operators can tell at a glance which docs came from a
 *   connector cron vs. a self-service upload.
 */
export type DocumentScope = "private" | "public" | "external"

export type Document = {
  filename: string
  s3_bucket: string
  s3_path: string
  /**
   * Phase 45.B — operator-chosen POSIX folder (`"/HR/"`,
   * `"/Finance/Q2/"`). Always present (defaults to `"/"` for legacy
   * docs uploaded before Phase 45.B). The /documents tree walks
   * this — NOT `s3_path` — to render a humanised hierarchy.
   */
  folder_path: string
  /** One of `private` / `public` / `external`. Drives the top-level
   *  bucket in the tree (My documents / Common / External). */
  scope: DocumentScope
  og_uri: string | null
  upload_datetime: string
  uploaded_by: string
  totalTokens: number
}