import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"
import { Document, DocumentScope, FileTree } from "./types/Document"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Top-level bucket labels for the /documents tree. These wrap each
 * doc's `scope` ("private" / "public" / "external") into a human
 * label the user understands, so the tree reads as
 *
 *   📁 My documents
 *     📁 HR
 *       📄 vacation-policy.md
 *   📁 Common documents
 *     📁 Finance / Q2
 *       📄 budget.xlsx
 *   📁 External sources
 *     📁 mock-sharepoint
 *       📄 policy.docx
 *
 * instead of the raw S3 key tree (`raw → <UUID> → filename`) the
 * Phase 28 implementation produced.
 */
const SCOPE_LABELS: Record<DocumentScope, string> = {
  private: "My documents",
  public: "Common documents",
  external: "External sources",
}

/** Display order so the tree always reads My → Common → External. */
const SCOPE_ORDER: DocumentScope[] = ["private", "public", "external"]

/**
 * Build a humanised, scope-grouped tree from the docs-list response.
 *
 * Top level = scope buckets (My documents / Common / External),
 * filtered to scopes that actually have at least one doc so empty
 * sections don't clutter the table.
 *
 * Within each bucket we walk the operator-chosen `folder_path`
 * (`"/HR/policies/"` → `HR → policies`) instead of the raw S3 key.
 * That key was the source of the `raw → <UUID> → filename` ugliness
 * because private docs are stored at
 * `s3://users/<user_id>/raw/<source_id>/<filename>` and the
 * legacy tree walked that path.
 *
 * Docs at root (`folder_path === "/"`) render directly under their
 * scope bucket. Legacy docs without `folder_path` (uploaded before
 * Phase 45.B) fall through with `/` via the backend's `coalesce`
 * so they land at the scope-bucket root rather than disappearing.
 */
export function buildFileTree(documents: Document[]): FileTree[] {
  const root: FileTree[] = []

  // Group by scope first so the top-level tree reflects the
  // ownership / origin of each doc, not the S3 key.
  for (const scope of SCOPE_ORDER) {
    const inScope = documents.filter((d) => d.scope === scope)
    if (inScope.length === 0) continue

    const scopeFolder: FileTree = {
      type: "folder",
      depth: 0,
      name: SCOPE_LABELS[scope],
      childrens: [],
      original: undefined,
    }
    root.push(scopeFolder)

    for (const doc of inScope) {
      // Phase 45.B canonical folder shape: leading + trailing slash.
      // Strip them then split. Empty segments → root-level doc.
      const folderPath = (doc.folder_path ?? "/").replace(/^\/+|\/+$/g, "")
      const segments = folderPath.length === 0 ? [] : folderPath.split("/")

      let currentLevel = scopeFolder.childrens
      let depth = 1 // depth 0 is the scope bucket itself

      for (const segment of segments) {
        let folder = currentLevel.find(
          (el) => el.type === "folder" && el.name === segment,
        )
        if (!folder) {
          folder = {
            type: "folder",
            depth,
            name: segment,
            childrens: [],
            original: undefined,
          }
          currentLevel.push(folder)
        }
        if (folder.type === "folder") {
          currentLevel = folder.childrens
          depth += 1
        }
      }

      currentLevel.push({
        type: "document",
        depth,
        name: doc.filename,
        childrens: undefined,
        original: doc,
      })
    }
  }

  return root
}
