import { Document } from "@/lib/types/Document"
import RequestError from "@/lib/types/RequestError";

async function getDocuments() {
  const response = await fetch('/api/general/v0/docs', {
    method: 'GET',
    credentials: 'same-origin'
  })

  if (!response.ok) {
    throw new RequestError(response.status, response.statusText)
  }

  return response.json() 
}

async function processDocuments(
  documents: {
    file: File,
    visibility_groups: string[],
    s3_bucket: "users" | "shared"
    s3_path: string,
    method: string,
    tables: boolean,
    images: boolean
    /** Phase 45.B — POSIX-style folder for KB organisation
     *  (`"/HR/"`, `"/Finance/Q2/"`). Defaults to `"/"` (root)
     *  when omitted. */
    folder_path?: string
  }[],
  socket_id?: string,
) {
  const formData = new FormData()

  if (socket_id) {
    formData.append('socket_id', socket_id)
  }

  documents.forEach((d, index) => {
    // Indexed multi-file form shape. Backend accepts both
    // `s3_path_${i}` and the legacy `s3_path${i}` spellings; we send
    // the underscore-separated form to match the rest of the suffix
    // pattern (the no-underscore spelling was a typo in the original
    // Carrara frontend).
    formData.append('file_' + index, d.file)
    formData.append('visibility_groups_' + index, d.visibility_groups.join(', '))
    formData.append('s3_bucket_' + index, d.s3_bucket)
    formData.append('s3_path_' + index, d.s3_path)
    formData.append('method_' + index, d.method)
    formData.append('tables_' + index, d.tables.toString())
    formData.append('images_' + index, d.images.toString())
    // Phase 45.B — folder_path (defaults to root). Backend
    // normalises via `services/knowledge/folders.py` so invalid
    // input degrades to `/` without breaking the upload.
    formData.append('folder_path_' + index, d.folder_path ?? '/')
  })
  const response = fetch('/api/general/v0/docs/process', {
    method: 'POST',
    body: formData,
    credentials: 'same-origin'
  })

  //throw new Error("test")
  return response
}

async function deleteDocument(document: Document) {
  const response = fetch(`/api/general/v0/docs/${document.s3_bucket}/${encodeURIComponent(document.s3_path)}/${encodeURIComponent(document.filename)}` , {
    method: 'DELETE',
    credentials: 'same-origin'
  })

  return response
}

export { getDocuments, processDocuments, deleteDocument }