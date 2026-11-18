import NewChatForm from "@/components/forms/chat/NewChatForm";
import ErrorAlert, { BasicError } from "@/components/ui/custom/error-alert";
import LoadingButton from "@/components/ui/custom/loading-button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Trans } from "@lingui/react/macro";
import { PropsWithChildren, useState } from "react";
import { useNavigate, useRevalidator } from "react-router-dom";

function NewChatDialog({ children }: PropsWithChildren) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<BasicError>()

  const navigate = useNavigate()
  const revalidator = useRevalidator()

  const handleDialog = (open: boolean) => {
    if (open) {
      setLoading(false)
      setError(undefined)
    }
    setOpen(open)
  }
  
  return (
    <Dialog open={open} onOpenChange={handleDialog}>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle><Trans>New chat</Trans></DialogTitle>
          <DialogDescription><Trans>Create new chat</Trans></DialogDescription>
        </DialogHeader>
        <NewChatForm
          formId="new_chat2"
          setLoading={setLoading}
          setError={setError}
          onSuccess={(_values, response) => {
            revalidator.revalidate()
            navigate('/chats/' + response.id)
            setOpen(false)
          }}
        />
        <ErrorAlert error={error} />
        <DialogFooter>
          <LoadingButton loading={loading} form="new_chat2" type="submit">
            <Trans>Create</Trans>
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default NewChatDialog