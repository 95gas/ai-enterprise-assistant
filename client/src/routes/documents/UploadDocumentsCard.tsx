import { processDocuments } from "@/api/document"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import ErrorAlert, { BasicError } from "@/components/ui/custom/error-alert"
import LoadingButton from "@/components/ui/custom/loading-button"
import { MultiSelect } from "@/components/ui/custom/multi-select"
import { FiletypeIcon, HumanReadableFileSize, StyledDropzone } from "@/components/ui/custom/styled-dropzone"
import SuccessAlert from "@/components/ui/custom/success-alert"
import { Form, FormControl, FormField, FormItem, FormMessage } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import useAuth from "@/lib/hooks/useAuth"
import useSocket from "@/lib/hooks/useSocket"
import { zodResolver } from "@hookform/resolvers/zod"
import { Trans } from "@lingui/react/macro"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { useRevalidator } from "react-router-dom"
import { z } from "zod"
import { t } from "@lingui/core/macro";

// Carrara-specific complete org-group catalogue. Previously the
// MultiSelect rendered every entry and disabled the ones the user
// wasn't a member of — but in deployments where `user.groups` doesn't
// overlap this list, every option is disabled and the form is
// unsubmittable. Phase 32 follow-up: derive the dropdown source from
// `user.groups` at render time instead (see `visibilityGroupItems`
// inside the component) so any deployment's users see the groups
// they're actually a member of.
//
// Kept here as a static fallback when the user object has no groups
// (e.g. a misconfigured OIDC provider that forgot to map groups).
const FALLBACK_VISIBILITY_GROUPS = [
  "hr italy",
  "share-commonit-rw",
  "share-financedogane-rw",
  "share-qualitydepartment-ro",
  "share-corporateimage-rw",
  "share-globalsourcng-auditors-ro",
  "share-lo-rw",
  "share-supplychainarea-rw",
  "share-budrivelinedrivers-rw",
  "share-crlogistica-rw",
  "share-globalsourcing-rw",
  "share-csr-rw",
  "share-engineering_and_innovation-rw",
  "agritalia-all",
  "argentina-all",
  "carraro-all",
  "carrarochina-all-users",
  "carrarona-all",
  "cil-all-users",
  "ctl-all-users",
  "poggiofiorito-all",
  "ricambi-all",
  "siap-all",
  "research-and-development",
  "user-support",
  "temp_finance-hq",
  "temp_hr-corporate",
  "temp_ricambi-sp",
  "temp_test"
].map(v => v.toLowerCase())


type ProgressEvent = {
  user_id?: string
  stage: "uploading" | "converting" | "embedding" | "indexing" | "ready" | "failed"
  source_id?: string
  filename?: string
  chunks_count?: number
  error?: string
}

function UploadDocumentsCard() {
  const { user } = useAuth()
  const socket = useSocket()
  const revalidator = useRevalidator()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<BasicError>()
  const [uploadSuccess, setUploadSuccess] = useState(false);
  // Phase 27.B+C.3: latest ingestion-progress event (per filename)
  // streamed from the backend during the synchronous upload request.
  // Rendered as a status banner above the form so the user sees the
  // pipeline advance through `uploading → converting → embedding →
  // indexing → ready / failed` instead of staring at a generic spinner.
  const [progressByFile, setProgressByFile] = useState<Record<string, ProgressEvent>>({})

  useEffect(() => {
    const onProgress = (data: ProgressEvent) => {
      // Filter by user_id when available so multi-tenant deployments
      // don't surface other users' uploads to the current user. The
      // backend always populates user_id; the falsy branch is defensive.
      if (data.user_id && user?.id && data.user_id !== user.id) return
      const key = data.filename ?? data.source_id ?? "unknown"
      setProgressByFile((prev) => ({ ...prev, [key]: data }))
    }
    socket.on("docs-progress", onProgress)
    return () => {
      socket.off("docs-progress", onProgress)
    }
  }, [socket, user?.id])

  const formSchema = z.object({
    documents: z.object({
      file: z.instanceof(File),
      visibility_groups: z.string().array().min(1, { message: t`Select at least one visibility group` }),
      s3_bucket: z.enum(["users", "shared"], { message: t`Select a storage` }),
      s3_path: z.string(),
      method: z.string(),
      tables: z.boolean(),
      images: z.boolean(),
      // Phase 45.B — POSIX-style folder for KB organisation.
      // Defaults to `/` (root); operator picks `/HR/`, `/Finance/Q2/`, etc.
      // Backend normalises in `services/knowledge/folders.py`.
      folder_path: z.string().regex(
        /^\/([A-Za-z0-9 _-]+\/){0,6}$/,
        { message: t`Folder must be POSIX-style (e.g. /HR/ or /Finance/Q2/)` },
      ).default("/"),
    }).array().min(1, { message: t`Upload at least one document`}),
  })

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      documents: []
    }
  })

  async function onSubmit(values: z.infer<typeof formSchema>) {
    setLoading(true)
    setError(undefined)
    setProgressByFile({})

    const req = await processDocuments(values.documents)
    setLoading(false)

    if (!req.ok) {
      // The backend's HTTPException returns `{detail: {error: {message: "..."}}}`
      // (FastAPI default envelope); the legacy Carrara backend used the flat
      // `{message: "..."}` shape. Read both so the user sees an actionable
      // reason instead of a bare "Error 400".
      const body = await req.json().catch(() => ({}))
      const reason =
        body?.detail?.error?.message
        ?? body?.detail?.message
        ?? body?.error?.message
        ?? body?.message
        ?? (typeof body?.detail === "string" ? body.detail : undefined)
        ?? t`Unknown error`
      setError({code: req.status, message: reason})
      setUploadSuccess(false)
    } else {
      revalidator.revalidate()
      setUploadSuccess(true)

      form.reset()
    }
  }

  function stageLabel(stage: ProgressEvent["stage"]): string {
    switch (stage) {
      case "uploading": return t`Uploading…`
      case "converting": return t`Converting to Markdown…`
      case "embedding": return t`Computing embeddings…`
      case "indexing": return t`Writing to knowledge graph…`
      case "ready": return t`Ready`
      case "failed": return t`Failed`
    }
  }

  const setValue = form.setValue
  const values = form.watch()

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle><Trans>Upload documents</Trans></CardTitle>
        <CardDescription><Trans>Upload documents to process</Trans></CardDescription>
      </CardHeader>
      <CardContent>
        {(loading || Object.keys(progressByFile).length > 0) && (
          <div className="mb-4 space-y-2 text-sm">
            {Object.values(progressByFile).map((p) => (
              <div
                key={p.filename ?? p.source_id}
                className={`flex items-center justify-between rounded-md border px-3 py-2 ${p.stage === "failed" ? "border-destructive bg-destructive/5" : p.stage === "ready" ? "border-emerald-600 bg-emerald-50" : "border-border"}`}
              >
                <span className="truncate">
                  <span className="font-medium">{p.filename ?? p.source_id}</span>
                  {" · "}
                  {stageLabel(p.stage)}
                  {p.chunks_count !== undefined && ` (${p.chunks_count} chunks)`}
                </span>
                {p.error && (
                  <span className="ml-2 text-xs text-destructive">{p.error}</span>
                )}
              </div>
            ))}
          </div>
        )}
        <Form {...form}>
          <form id="upload_documents" onSubmit={form.handleSubmit(onSubmit)}>
            <FormField
              control={form.control}
              name="documents"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <StyledDropzone
                      value={field.value.map(v => v.file)}
                      onDrop={(files) => field.onChange(files.map(file => ({
                        file,
                        visibility_groups: form.getValues("documents").find(document => document.file.name === file.name)?.visibility_groups ?? [],
                        s3_bucket: "",
                        s3_path: "",
                        method: "full",
                        tables: true,
                        images: true,
                        folder_path: "/",
                      })))}
                      accept={{
                        // pdf
                        "application/pdf": [],
                        // excel
                        "application/vnd.ms-excel": [],
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [],
                        // msword
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [],
                        "application/msword": [],
                        // csv
                        "text/csv": [],
                        // xml
                        "text/xml": [],
                        // ppt
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation": [],
                        "application/vnd.ms-powerpoint" : [],
                        // markdown
                        "text/plain": [".md", ".dat"],
                        // eml
                        "message/rfc822": [],
                        // images
                        "image/jpeg": [],
                        // audio
                        "audio/mpeg": [],
                        // video
                        "video/mp4":[],
                    }}
                      renderFile={(file, index) => (
                        <div className="flex space-x-2 items-start">
                          <div className="text-sm flex flex-1 items-center border rounded-md p-2">
                            <FiletypeIcon type={file.type} />
                            <span className="max-w-48 overflow-hidden text-ellipsis">
                              {file.name}
                            </span>
                            <span className="ml-auto">
                              <HumanReadableFileSize size={file.size} />
                            </span>
                          </div>
                        <FormField
                          control={form.control}
                          name={`documents.${index}.s3_bucket`}
                          render={({ field }) => (
                            <FormItem>
                              <FormControl>
                                <Select
                                  value={field.value}
                                  onValueChange={(newValue) => {
                                    field.onChange(newValue)
                                    if (newValue === "users") {
                                      setValue(`documents.${index}.s3_path`, user?.email ?? "")
                                      setValue(`documents.${index}.visibility_groups`, ["private"])
                                    } else {
                                      setValue(`documents.${index}.s3_path`, "Common")
                                      setValue(`documents.${index}.visibility_groups`, [])
                                    }
                                  }}
                                >
                                  <SelectTrigger className="w-48 bg-transparent">
                                    <SelectValue placeholder={t`Select storage`} />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {user?.permissions?.upload_private && (
                                      <SelectItem value={"users"}>
                                        <Trans>Private</Trans>
                                      </SelectItem>
                                    )}
                                    {user?.permissions?.upload_common && (
                                      <SelectItem value={"shared"}>
                                        <Trans>Common</Trans>
                                      </SelectItem>
                                    )}
                                  </SelectContent>
                                </Select>
                              </FormControl>
                              <FormMessage className="max-w-48 text-wrap" />
                            </FormItem>
                          )}
                        />
                        {values.documents[index].s3_bucket !== "users" && (
                          <FormField
                            control={form.control}
                            name={`documents.${index}.visibility_groups`}
                            render={({ field }) => (
                              <FormItem>
                                <FormControl>
                                  <MultiSelect
                                    searchable
                                    items={
                                      // Prefer the user's actual groups (always selectable —
                                      // a user can only grant access to groups they belong
                                      // to). Fall back to the Carrara catalogue when the
                                      // user object has no groups so legacy deployments
                                      // still render a populated dropdown.
                                      ((user?.groups?.length ?? 0) > 0
                                        ? (user?.groups ?? [])
                                        : FALLBACK_VISIBILITY_GROUPS
                                      ).map(p => ({
                                        id: p,
                                        label: p,
                                        disabled: false,
                                      }))
                                    }
                                    objectName={"visibility_group"}
                                    values={field.value.map(v => ({ id: v, label: v }))}
                                    onValuesChange={(values) => {
                                      field.onChange(values.map(v => v.id))
                                    }}
                                    buttonClassName="w-48"
                                    popoverClassName="w-48"
                                  />
                                </FormControl>
                                <FormMessage className="max-w-48 text-wrap" />
                              </FormItem>
                            )}
                          />
                        )}
                        {/* Phase 45.B — POSIX folder picker. Defaults to
                            `/` (root); operator types `/HR/`,
                            `/Finance/Q2/`, etc. Backend normalises in
                            `services/knowledge/folders.py`; invalid
                            input degrades to `/` server-side. */}
                        <FormField
                          control={form.control}
                          name={`documents.${index}.folder_path`}
                          render={({ field }) => (
                            <FormItem>
                              <FormControl>
                                <Input
                                  placeholder="/HR/policies/"
                                  value={field.value ?? "/"}
                                  onChange={(e) => field.onChange(e.target.value)}
                                  className="w-40 font-mono text-xs"
                                  data-testid={`folder-path-${index}`}
                                />
                              </FormControl>
                              <FormMessage className="max-w-40 text-wrap" />
                            </FormItem>
                          )}
                        />
                        </div>
                      )}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>
        {uploadSuccess ? <SuccessAlert className="mt-4"><Trans>Documents processed and uploaded correctly!</Trans></SuccessAlert>: <></>}
        <ErrorAlert error={error} className="mt-4" />
      </CardContent>
      <CardFooter>
        <LoadingButton loading={loading} form="upload_documents" type="submit">
          <Trans>Upload</Trans>
        </LoadingButton>
      </CardFooter>
    </Card>
  )
}

export default UploadDocumentsCard