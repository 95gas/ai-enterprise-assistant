import { Folder, Maximize2, Minimize2, Send } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { useEffect, useState, Suspense } from "react";
import DocumentSelectorDialog from "./DocumentSelectorDialog";
import { Document } from "@/lib/types/Document";
import { TypographyMuted } from "../ui/typography/muted";
import { Trans } from "@lingui/react/macro";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Model } from "@/lib/types/Model";
import { t } from "@lingui/core/macro";
import { Workflow } from "@/lib/types/Message";
import { Switch } from "../ui/switch";
import { Label } from "../ui/label";
import { Separator } from "../ui/separator";
import { Await, useLoaderData } from "react-router-dom";
import { Skeleton } from "../ui/skeleton";
import useAuth from "@/lib/hooks/useAuth";
import useFeatureFlags from "@/lib/hooks/useFeatureFlags";

const whitespaceRegex = /\S/

// NOTE: this must be used inside a relative ScrollArea
function ChatTextbox({message, setMessage, models, selectedModel, setSelectedModel, workflow, setWorkflow: _setWorkflow, loading, selectedDocuments, setSelectedDocuments, internalKnowledge, setInternalKnowledge, docSearch, setDocSearch, webSearch, setWebSearch, onSend, checkpoint, setCheckpoint, disabled}: {
  message: string
  setMessage: (message: string) => void
  models: Model[],
  selectedModel: Model | undefined,
  setSelectedModel: (value: Model) => void,
  workflow: Workflow,
  setWorkflow: (workflow: Workflow) => void,
  selectedDocuments: Document[],
  setSelectedDocuments: (document: Document[]) => void,
  internalKnowledge: boolean,
  setInternalKnowledge: (value: boolean) => void,
  docSearch: boolean,
  setDocSearch: (value: boolean) => void,
  webSearch: boolean,
  setWebSearch: (value: boolean) => void,
  loading: boolean
  onSend: () => Promise<void>
  checkpoint: number | undefined,
  setCheckpoint: (value: number | undefined) => void,
  disabled?: boolean
}) {
  const { user } = useAuth()
  // Phase 50.A — server-authoritative feature-flag snapshot. Phase
  // 59.G retired the workflow dropdown so the `admin_agent_enabled`
  // flag is no longer read inline; the AdminAssistant app is
  // reachable via the Apps sidebar (Phase 59.D /apps endpoint) when
  // the user is in the admin group. The hook stays imported for
  // future per-feature gates that might need the snapshot.
  useFeatureFlags()
  const data = useLoaderData() as unknown as { documents: Document[] }
  const [maximize, setMaximize] = useState(false)
  const focusMode = workflow === "FocusMode"
  const overMaxLength = (message.length / 4) > Math.floor((selectedModel?.context_window ?? 0) / 4)
  const overMaxDocuments = focusMode && selectedDocuments.reduce((p, c) => p + c.totalTokens, 0) > Math.floor((selectedModel?.context_window ?? 0) / 4)
  const disableSend = !whitespaceRegex.test(message) || overMaxLength || loading || selectedModel === undefined || (focusMode && selectedDocuments.length === 0) || !(internalKnowledge || docSearch || webSearch)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const key = e.key
    const shiftKey = e.shiftKey

    if (key === "Enter" && shiftKey === false) {
      e.preventDefault()
      if (!disableSend) {
        setMaximize(false)
        onSend()
      }
    }
  }

  const handleClick = () => {
    setMaximize(false)
    onSend()
  }

  useEffect(() => {
    if (selectedDocuments.length > 0) {
      setDocSearch(true)
    }
  }, [selectedDocuments, setDocSearch])

  return (
  <div className="flex flex-col items-center absolute bottom-0 pb-4 w-full bg-gradient-to-t from-90% from-background">
    {checkpoint !== undefined && (
      <div className="w-full max-w-[58rem] mb-2 px-4 flex items-center rounded-md shadow-xl bg-card border border-border ">
        <TypographyMuted><Trans>You are editing a message, any following messages from the selected will be deleted.</Trans></TypographyMuted>
        <Button variant="link" size="sm" onClick={() => setCheckpoint(undefined)}><Trans>Cancel</Trans></Button>
      </div>
    )}
    <div className="w-full max-w-[58rem] mb-4 p-4 flex flex-col gap-4 rounded-md shadow-xl bg-card border border-border ring-offset-background focus-within:outline-none focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2">
      <Textarea
        disabled={disabled}
        className="border-none resize-none p-0 ring-offset-card bg-card focus-visible:ring-card focus-visible:ring-0"
        placeholder={import.meta.env.VITE_NAME}
        value={message}
        rows={maximize ? 40 : 6}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <div className="flex flex-row justify-between">
        <div className="flex flex-row flex-wrap gap-3 items-center">
          <Select disabled={disabled} value={(selectedModel?.provider ?? "") + (selectedModel?.model ?? "")} onValueChange={(value) => setSelectedModel(models.find(model => (model.provider + model.model) === value)!)}>
            <SelectTrigger className="w-36 bg-transparent [&_[data-desc]]:hidden">
              <SelectValue placeholder={t`Select your model`}/>
            </SelectTrigger>
            <SelectContent>
              {models.map(model => (
                <SelectItem disabled={model.tot_tokens_timeframe >= model.tokens_limit} key={model.provider + model.model} value={model.provider + model.model}>
                  <Trans>{model.model} <span className="mt-1 block text-xs text-muted-foreground" data-desc>{model.provider}, usage {Math.min(Math.ceil((model.tot_tokens_timeframe / model.tokens_limit) * 100), 100)}%</span></Trans>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {/* Phase 59.G — workflow dropdown retired. The General
              orchestrator (Phase 59.C) auto-builds its tool/MCP/
              sub-agent fleet from the caller's visibility groups +
              consults corporate policy on every turn, so the user
              no longer needs to pick a workflow. FocusMode is the
              only remaining client-side toggle (selected documents
              → forced doc_search) and is set automatically when
              the user picks documents below; no UI surface needed
              here. AdminAssistant is reachable through the Apps
              sidebar (Phase 59.D /apps endpoint) when the user is
              in the admin group. */}
          {/* Safely check permissions using optional chaining */}
          {user?.permissions?.doc_search && (
            <Suspense
              fallback={<Skeleton className="h-10 w-44" />}
            >
              <Await resolve={data.documents} errorElement={"error"}>
                {(documents: Document[]) => (
                  <DocumentSelectorDialog documents={documents} showTokens={focusMode} overMaxDocuments={overMaxDocuments} selectedModel={selectedModel} selectedDocuments={selectedDocuments} setSelectedDocuments={setSelectedDocuments}>
                    <Button variant={"outline"} disabled={disabled}>
                      <Folder/> <Trans>Documents {selectedDocuments.length > 0 && `(${selectedDocuments.length})`}</Trans>
                    </Button>
                  </DocumentSelectorDialog>
                )}
              </Await>
            </Suspense>
          )}
          {(message.length >= 100 || maximize) && (
            <Button size="icon" variant={"outline"} onClick={() => setMaximize(!maximize)}>
              {maximize ? <Minimize2 className="h-4 w-4"/> : <Maximize2 className="h-4 w-4"/>}
            </Button>
          )}
          {overMaxLength && (
            <p className="text-destructive "><Trans>Message is over the maximum allowed length</Trans></p>
          )}
          {overMaxDocuments && (
            <p className="text-destructive "><Trans>Selected documents are over the maximum allowed length</Trans></p>
          )}
          <div className="flex gap-3 border rounded-md h-10 items-center px-3">
            <div className="flex items-center gap-2">
              <Switch checked={internalKnowledge} onCheckedChange={setInternalKnowledge}/>
              <Label>
                <Trans>Model</Trans>
              </Label>
            </div>
            {/* Safely check permissions using optional chaining */}
            {user?.permissions?.doc_search && (
              <>
                <Separator orientation="vertical" className="h-6" />
                <div className="flex items-center gap-2">
                  <Switch checked={docSearch} onCheckedChange={setDocSearch} />
                  <Label>
                    <Trans>Docs</Trans>
                  </Label>
                </div>
              </>
            )}
            {/* Safely check permissions using optional chaining */}
            {user?.permissions?.web_search && (
              <>
                <Separator orientation="vertical" className="h-6" />
                <div className="flex items-center gap-2">
                  <Switch checked={webSearch} onCheckedChange={setWebSearch} />
                  <Label>
                    <Trans>Web</Trans>
                  </Label>
                </div>
              </>
            )}
          </div>
        </div>
        <Button size="icon" onClick={handleClick} disabled={disableSend}>
          <Send className="h-4 w-4"/>
        </Button>
      </div>
    </div>
    <TypographyMuted>
      <Trans>Keep in mind that {import.meta.env.VITE_NAME} uses AI. Always double check important information.</Trans>
    </TypographyMuted>
  </div>
  )
}

export default ChatTextbox