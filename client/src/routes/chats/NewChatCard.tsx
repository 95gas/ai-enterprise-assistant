import NewChatForm from "@/components/forms/chat/NewChatForm";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import ErrorAlert, { BasicError } from "@/components/ui/custom/error-alert";
import LoadingButton from "@/components/ui/custom/loading-button";
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { useNavigate, useRevalidator } from "react-router-dom";

function NewChatCard() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<BasicError>()

  const navigate = useNavigate()
  const revalidator = useRevalidator()
  
  return (
    <Card>
      <CardHeader>
        <CardTitle><Trans>New chat</Trans></CardTitle>
        <CardDescription><Trans>Create new chat</Trans></CardDescription>
      </CardHeader>
      <CardContent>
        <NewChatForm
          formId="new_chat"
          setLoading={setLoading}
          setError={setError}
          onSuccess={(_values, response) => {
            revalidator.revalidate()
            navigate('/chats/' + response.id)
          }}
        />
        <ErrorAlert error={error} className="mt-4" />
      </CardContent>
      <CardFooter>
        <LoadingButton loading={loading} form="new_chat" type="submit">
          <Trans>Create</Trans>
        </LoadingButton>
      </CardFooter>
    </Card>
  )
}

export default NewChatCard