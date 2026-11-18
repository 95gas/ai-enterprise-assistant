import { z } from "zod"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "../../ui/form"
import { Input } from "../../ui/input"
import { BasicError } from "@/components/ui/custom/error-alert"
import { newChat } from "@/api/chat"
import { Chat } from "@/lib/types/Chat"
import { t } from "@lingui/core/macro"
import { Trans } from "@lingui/react/macro"

function NewChatForm({ formId, setLoading, setError, onSuccess }: {
  formId: string,
  setLoading: (open: boolean) => void,
  setError: (error: BasicError | undefined) => void,
  onSuccess: (values: { name: string }, response: { id: string }) => void
}) {
  const formSchema = z.object({
    name: z.string().min(1, { message: t`Name required`})
  })

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: ""
    }
  })

  async function onSubmit(chatName: z.infer<typeof formSchema>) {
    setLoading(true)
    setError(undefined)
    const new_chat_req = await newChat(chatName.name) 

    if (!new_chat_req.ok) {
      setError({code: new_chat_req.status, message: new_chat_req.statusText})
    } else {
      const res = (await new_chat_req.json()) as Chat
      const resp_id = {"id" : res.id.toString()}
      onSuccess(chatName, resp_id)
      form.reset()
    }
    setLoading(false)

  }

  return (
    <Form {...form}>
      <form id={formId} onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel><Trans>Chat name</Trans></FormLabel>
              <FormControl>
                <Input className="bg-card ring-offset-card" placeholder={t`Chat name`} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </form>
    </Form>
  )
}

export default NewChatForm