import { AlertCircle } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "../alert"

export type BasicError = {
  code: number | undefined,
  message: string
}

function ErrorAlert({ error, className }: {
  error: BasicError | undefined
  className?: string
}) {
  if (error) {
    return (
      <Alert variant="destructive" className={className}>
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Error {error.code}</AlertTitle>
        <AlertDescription>
          {error.message}
        </AlertDescription>
      </Alert>
    )
  } else {
    return (<></>)
  }

}

export default ErrorAlert