import { PropsWithChildren, useCallback, useEffect, useState } from "react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "../alert-dialog";
import ErrorAlert, { BasicError } from "./error-alert";
import { useRevalidator } from "react-router-dom";
import LoadingButton from "./loading-button";
import SuccessAlert from "./success-alert";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";

type ConfirmDialogProps = PropsWithChildren & {
  action: "delete" | "logout"
  objectName: string,
  onSubmit: () => Promise<Response>
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

function ConfirmDialog({ action, objectName, onSubmit, children, open, onOpenChange }: ConfirmDialogProps) {
  const revalidator = useRevalidator()

  function getActionText(action: ConfirmDialogProps["action"], objectName: ConfirmDialogProps["objectName"]) {
    switch (action) {
      case "delete":
        return {
          title: t`Delete ${objectName}`,
          subtitle: t`Are you sure you want to delete ${objectName}?`,
          success: t`Deleted ${objectName} correctly`
        }
        
      case "logout": 
        return {
          title: t`Log out user '${objectName}'`,
          subtitle: t`Are you sure you want to log out of ASK?`,
          success: t`Log out user '${objectName}' completed correctly.`
        }
    }
  }

  const [internalOpen, setInternalOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<BasicError>()
  const actionText = getActionText(action, objectName)

  const handleSubmit = async () => {
    setLoading(true)
    setError(undefined)
    const req = await onSubmit()
    setLoading(false)

    if (!req.ok) {
      setError({code: req.status, message: req.statusText})
    } else {
      setSuccess(true)
    }
  }

  const handleDialog = useCallback((open: boolean) => {
    if (open) {
      setLoading(false)
      setSuccess(false)
      setError(undefined)
    } else if (success) {
      revalidator.revalidate()
    }

    setInternalOpen(open)
    if (onOpenChange) {
      onOpenChange(open)
    }
  }, [onOpenChange, revalidator, success])

  useEffect(() => {
    if (open) {
      setInternalOpen(open)
      handleDialog(open)
    }
  }, [open, handleDialog])

  return (
    <AlertDialog open={internalOpen} onOpenChange={handleDialog}>
      <AlertDialogTrigger asChild>
        {children}
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {actionText.title}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {actionText.subtitle}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {success && <SuccessAlert className="mt-4">{actionText.success}</SuccessAlert>}
        <ErrorAlert error={error} />
        <AlertDialogFooter>
          <AlertDialogCancel><Trans>Cancel</Trans></AlertDialogCancel>
          {success
            ? <AlertDialogAction><Trans>Continue</Trans></AlertDialogAction>
            : <LoadingButton onClick={handleSubmit} loading={loading}><Trans>Continue</Trans></LoadingButton>
          }
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default ConfirmDialog