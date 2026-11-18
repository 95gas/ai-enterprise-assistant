import { Link, useRouteError, isRouteErrorResponse } from "react-router-dom"
import { Button } from "../components/ui/button"
import { Trans } from "@lingui/react/macro"

function NotFoundPage() {
  const error = useRouteError()

  // This prints the exact crash to your browser's F12 console
  console.error("REACT ROUTER CAUGHT AN ERROR:", error)

  // If it's a genuine 404 (the URL actually doesn't exist)
  if (isRouteErrorResponse(error)) {
    return (
      <div className="flex w-full h-screen justify-center items-center">
        <div className="flex flex-col items-center space-y-4">
          <h3 className="scroll-m-20 text-2xl font-semibold tracking-tight">
            <Trans>Error 404: Page not found</Trans>
          </h3>
          <Link to="/">
            <Button variant="ghost">
              <Trans>Back to Home</Trans>
            </Button>
          </Link>
        </div>
      </div>
    )
  }

  // If a component exploded, show us why!
  return (
    <div className="flex w-full h-screen justify-center items-center">
      <div className="flex flex-col items-center space-y-4 max-w-2xl text-center">
        <h3 className="scroll-m-20 text-2xl font-semibold tracking-tight text-red-500">
          500: The App Crashed!
        </h3>
        <p className="text-muted-foreground">
          Check your browser's developer console (F12) for the full stack trace.
        </p>
        <pre className="bg-secondary p-4 rounded-md text-sm text-left overflow-auto w-full text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </pre>
        <Link to="/">
          <Button variant="outline">
            <Trans>Back to Home</Trans>
          </Button>
        </Link>
      </div>
    </div>
  )
}

export default NotFoundPage