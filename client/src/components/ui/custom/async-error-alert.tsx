import RequestError from "@/lib/types/RequestError";
import { useAsyncError } from "react-router-dom";
import ErrorAlert from "./error-alert";

function AsyncErrorAlert() {
  const error = useAsyncError()

  if (error instanceof RequestError) {
    return <ErrorAlert error={error} />
  }

  return (
    <ErrorAlert error={{
      code: undefined,
      message: (error as Error).message
    }}/>
  )
}

export default AsyncErrorAlert