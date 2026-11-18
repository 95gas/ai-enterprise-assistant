import { chatFeedback } from "@/api/chat";
import { Button } from "@/components/ui/button";
import ErrorAlert, { BasicError } from "@/components/ui/custom/error-alert";
import LoadingButton from "@/components/ui/custom/loading-button";
import SuccessAlert from "@/components/ui/custom/success-alert";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Message } from "@/lib/types/Message";
import { zodResolver } from "@hookform/resolvers/zod";
import { DialogTrigger } from "@radix-ui/react-dialog";
import { PropsWithChildren, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";



function ChatFeedbackDialog({ messageIndex, chatId, fullChat, children }: PropsWithChildren & { messageIndex: number, chatId: string, fullChat: Message[] }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<BasicError>()

  const handleDialog = (open: boolean) => {
    if (open) {
      setLoading(false)
      setSuccess(false)
      setError(undefined)
      form.reset()
    }
    setOpen(open)
  }

  const formSchema = z.object({
    useful_answers: z.boolean(),
    understandable_answers: z.boolean(),
    relevant_sources: z.boolean(),
    other_comments: z.string().max(500, { message: t`Message is over the maximum allowed length (${"500"} characters)` })
  })

  function concat_answers_chat(answers: z.infer<typeof formSchema>, full_chat: Message[], message_index: number){
  return {
    useful_answers: answers.useful_answers,
    understandable_answers: answers.understandable_answers,
    relevant_sources: answers.relevant_sources,
    other_comments: answers.other_comments,
    message_index: message_index,
    conversation: full_chat
  }
}

  const form = useForm<z.infer<typeof formSchema>> ({
    resolver: zodResolver(formSchema),
    defaultValues: {
      useful_answers: false,
      understandable_answers: false,
      relevant_sources: false,
      other_comments: ""
    }
  })

  async function onSubmit(values: z.infer<typeof formSchema>) {
    setLoading(true)
    setError(undefined)

    const full_feedback = concat_answers_chat(values, fullChat, messageIndex)

    const req = await chatFeedback(chatId, full_feedback)
    setLoading(false)
    if (!req.ok) {
      setError({code: req.status, message: req.statusText})
    } else {
      setSuccess(true)
      form.reset()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleDialog}>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle><Trans>Feedback</Trans></DialogTitle>
          <DialogDescription><Trans>Provide a feedback to improve the conversation</Trans></DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form id="chat_feedback" onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
            <FormField
              control={form.control}
              name="useful_answers"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base"><Trans>Useful answer</Trans></FormLabel>
                    <FormDescription><Trans>Did the message answer your question in a complete and informative way?</Trans></FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="understandable_answers"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base"><Trans>Understandable answer</Trans></FormLabel>
                    <FormDescription><Trans>Was the provided answer easy to understand?</Trans></FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="relevant_sources"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base"><Trans>Relevant sources</Trans></FormLabel>
                    <FormDescription><Trans>Were the sources found relevant to your questions?</Trans></FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="other_comments"
              render={({ field }) => (
                <FormItem>
                  <FormLabel><Trans>Other comments</Trans></FormLabel>
                  <FormControl>
                    <Textarea placeholder={t`Other comments`} {...field} rows={5}/>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>
        {success && <SuccessAlert><Trans>Feedback correctly submitted</Trans></SuccessAlert>}
        <ErrorAlert error={error} />
        <DialogFooter>
          {success
            ? <Button onClick={() => handleDialog(false)}><Trans>Continue</Trans></Button>
            : <LoadingButton loading={loading} form="chat_feedback" type="submit"><Trans>Submit</Trans></LoadingButton>
          }
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ChatFeedbackDialog