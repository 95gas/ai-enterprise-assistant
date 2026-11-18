import { CircleCheck } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "../alert"
import { PropsWithChildren } from "react"
import { Trans } from "@lingui/react/macro"

function SuccessAlert({ children,  className }: PropsWithChildren & {
  className?: string
}) {
  return (
    <Alert variant="success" className={className}>
      <CircleCheck className="h-4 w-4" />
      <AlertTitle><Trans>Success</Trans></AlertTitle>
      <AlertDescription>
        {children}
      </AlertDescription>
    </Alert>
  )
}

export default SuccessAlert