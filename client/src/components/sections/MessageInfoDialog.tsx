import { AssistantMessage, MessageMode, UserMessage } from "@/lib/types/Message";
import { PropsWithChildren } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog";
import { Plural, Select, Trans } from "@lingui/react/macro";
import { ScrollArea, ScrollBar } from "../ui/scroll-area";

function MessageInfoDialog({ userMessage, assistantMessage, children }: PropsWithChildren & { userMessage: UserMessage, assistantMessage: AssistantMessage }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle><Trans>Message information</Trans></DialogTitle>
          <DialogDescription><Trans>Information of the selected message</Trans></DialogDescription>
        </DialogHeader>
        <ScrollArea>
          <div className="space-y-2 max-h-96">
            <div><Trans>Question: {userMessage.content}</Trans></div>
            <div><Trans>Mode: <Select value={userMessage.mode} _chat={"Chat"} _search={"Search"} _focus={"Focus"} other={"Unknown"}/></Trans></div>
            <div><Trans>Used tokens: {assistantMessage.metadata.input_tokens} (input), {assistantMessage.metadata.output_tokens} (output)</Trans></div>
            <div><Trans>LLM model: {assistantMessage.metadata.llm_model}</Trans></div>
            {userMessage.mode !== MessageMode.Chat && (
              <div>
                <Trans>
                  Requested sources:
                  <ul className="ml-6 list-disc [&>li]:mt-2">
                    <Plural
                      value={userMessage.documents?.length ?? 0}
                      _0={<li>{"None"}</li>}
                      other={(userMessage.documents ?? []).map(d => <li key={d.filename}>{ d.filename }</li>)}
                    />
                  </ul>
                </Trans>
              </div>
            )}
            {userMessage.mode !== MessageMode.Chat && (
              <div>
                <Trans>
                  Used sources:
                  <ul className="ml-6 list-disc [&>li]:mt-2">
                    <Plural
                      value={assistantMessage.sources?.length ?? 0}
                      _0={<li>{"None"}</li>}
                      other={assistantMessage.sources?.map(d => <li key={d.filename}>{ d.filename }</li>)}
                    />
                  </ul>
                </Trans>
              </div>
            )}
          </div>
          <ScrollBar orientation="vertical" />
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

export default MessageInfoDialog