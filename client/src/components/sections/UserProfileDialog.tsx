import { PropsWithChildren, useCallback, useEffect, useState } from "react";
import ErrorAlert, { BasicError } from "../ui/custom/error-alert";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog";
import useAuth from "@/lib/hooks/useAuth";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "../ui/form";
import { Input } from "../ui/input";
import SuccessAlert from "../ui/custom/success-alert";
import { Button } from "../ui/button";
import LoadingButton from "../ui/custom/loading-button";
import { MultiSelect } from "../ui/custom/multi-select";
import { t } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { Calendar } from "../ui/calendar";
import { ChevronDown } from "lucide-react";
import { Checkbox } from "../ui/checkbox";

const visibility_groups = [
    "hr italy",
    "share-commonit-rw",
    "share-financedogane-rw",
    "share-qualitydepartment-ro",
    "share-corporateimage-rw",
    "share-globalsourcng-auditors-ro",
    "share-lo-rw",
    "share-supplychainarea-rw",
    "share-budrivelinedrivers-rw",
    "share-crlogistica-rw",
    "share-globalsourcing-rw",
    "share-csr-rw",
    "share-engineering_and_innovation-rw",
    "agritalia-all",
    "argentina-all",
    "carraro-all",
    "carrarochina-all-users",
    "carrarona-all",
    "cil-all-users",
    "ctl-all-users",
    "poggiofiorito-all",
    "ricambi-all",
    "siap-all",
    "research-and-development",
    "user-support",
    "temp_finance-hq",
    "temp_hr-corporate",
    "temp_ricambi-sp",
    "temp_test",
].map(v => v.toLowerCase())

function UserProfileDialog({ children, open, onOpenChange }: PropsWithChildren & {
  open?: boolean,
  onOpenChange?: (open: boolean) => void
}) {
  const { i18n } = useLingui()
  const { user, update } = useAuth()
  const [internalOpen, setInternalOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<BasicError>()
  
  const formSchema = z.object({
    email: z.string().min(1, { message: t`E-mail required` }).email({ message: t`E-mail is not valid` }),
    name: z.string().min(1, { message: t`Name required`}),
    groups: z.string().array().min(1, { message: t`Select at least one group` }),
    domain: z.string().min(1, { message: t`Domain required` }),
    permissions: z.object({
      web_search: z.boolean(),
      doc_search: z.boolean(),
      upload_common: z.boolean(),
      upload_private: z.boolean(),
      app_name: z.boolean()
    }),
    last_login: z.string(),
    tot_token_limit: z.number(),
    tot_limit_reset_period: z.string(),
    expiring_date_trial: z.date()
  })

  const form = useForm<z.infer<typeof formSchema>> ({
    resolver: zodResolver(formSchema),
    defaultValues: {
      email: user?.email,
      name: user?.name,
      groups: user?.groups,
      domain: user?.domain,
      permissions: user?.permissions,
      last_login: user?.last_login,
      tot_token_limit: user?.tot_token_limit,
      tot_limit_reset_period: user?.tot_limit_reset_period,
      expiring_date_trial: user?.expiring_date_trial ? new Date(user.expiring_date_trial) : undefined
    }
  })

  const handleDialog = useCallback((open: boolean) => {
    if (open) {
      setLoading(false)
      setSuccess(false)
      setError(undefined)
      form.reset()
    }

    setInternalOpen(open)
    if (onOpenChange) {
      onOpenChange(open)
    }
  }, [form, onOpenChange])

  useEffect(() => {
    if (open) {
      setInternalOpen(open)
      handleDialog(open)
    }
  }, [open, handleDialog])

  async function onSubmit(values: z.infer<typeof formSchema>) {
    setLoading(true)
    const res = await update({
      ...values,
      expiring_date_trial: values.expiring_date_trial.toUTCString()
    })
    setLoading(false)

    if (!res.ok) {
      setError({ code: res.status, message: res.statusText })
    } else {
      setSuccess(true)
      form.reset()
    }
  }

  // TODO: decide what is disabled based on the domain and env
  return (
    <Dialog open={internalOpen} onOpenChange={handleDialog}>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle><Trans>Profile</Trans></DialogTitle>
          <DialogDescription><Trans>Access your user profile details</Trans></DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form id="user_profile" onSubmit={form.handleSubmit(onSubmit)} className="grid grid-cols-2 gap-4">
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel><Trans>E-mail</Trans></FormLabel>
                  <FormControl>
                    <Input {...field} disabled />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel><Trans>Name</Trans></FormLabel>
                  <FormControl>
                    <Input {...field} disabled />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="col-span-2 space-y-2">
              <p>Permissions</p>
              <div className="border rounded-md p-3 space-y-2">
                <FormField
                  control={form.control}
                  name="permissions.web_search"
                  render={({ field }) => (
                    <FormItem className="flex items-center space-y-0 space-x-2">
                      <FormControl>
                        <Checkbox
                          disabled
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <FormLabel><Trans>Web search</Trans></FormLabel>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="permissions.doc_search"
                  render={({ field }) => (
                    <FormItem className="flex items-center space-y-0 space-x-2">
                      <FormControl>
                        <Checkbox
                          disabled
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <FormLabel><Trans>Document search</Trans></FormLabel>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="permissions.upload_common"
                  render={({ field }) => (
                    <FormItem className="flex items-center space-y-0 space-x-2">
                      <FormControl>
                        <Checkbox
                          disabled
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <FormLabel><Trans>Upload common</Trans></FormLabel>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="permissions.upload_private"
                  render={({ field }) => (
                    <FormItem className="flex items-center space-y-0 space-x-2">
                      <FormControl>
                        <Checkbox
                          disabled
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <FormLabel><Trans>Upload private</Trans></FormLabel>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                {/* <FormField
                  control={form.control}
                  name="permissions.app_name"
                  render={({ field }) => (
                    <FormItem className="flex items-center space-y-0 space-x-2">
                      <FormControl>
                        <Checkbox
                          disabled
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <FormLabel><Trans>App name</Trans></FormLabel>
                      <FormMessage />
                    </FormItem>
                  )}
                /> */}
              </div>
            </div>
            <FormField
              control={form.control}
              name="groups"
              render={({ field }) => (
                <FormItem className="flex flex-col col-span-2">
                  <FormLabel><Trans>Groups</Trans></FormLabel>
                  <FormControl>
                    <MultiSelect
                      disabled
                      searchable
                      items={visibility_groups.map(p => ({id: p, label: p}))}
                      objectName={t`Groups`}
                      values={field.value.map(v => ({id: v, label: v}))}
                      onValuesChange={(values) => {field.onChange(values.map(v => v.id))}}
                      
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="domain"
              render={({ field }) => (
                <FormItem className="col-span-2">
                  <FormLabel><Trans>Domain</Trans></FormLabel>
                  <FormControl>
                    <Input {...field} disabled />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="tot_token_limit"
              render={({ field }) => (
                <FormItem>
                  <FormLabel><Trans>Total tokens limit</Trans></FormLabel>
                  <FormControl>
                    <Input {...field} disabled />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="tot_limit_reset_period"
              render={({ field }) => (
                <FormItem>
                  <FormLabel><Trans>Total tokens reset period</Trans></FormLabel>
                  <FormControl>
                    <Input {...field} disabled />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="expiring_date_trial"
              render={({ field }) => (
                <FormItem className="flex flex-col col-span-2">
                  <FormLabel><Trans>Trial expiry date</Trans></FormLabel>
                  <Popover modal={true}>
                    <PopoverTrigger asChild>
                      <FormControl>
                        <Button variant="outline" role="combobox" disabled>
                          <div className="w-full flex text-start">
                            {i18n.date(field.value, { 
                              dateStyle: "long"
                            })}
                          </div>
                          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                      </FormControl>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={field.value}
                        onSelect={field.onChange}
                        captionLayout="dropdown"
                      />
                    </PopoverContent>
                  </Popover>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>
        {success && <SuccessAlert><Trans>Profile correctly updated</Trans></SuccessAlert>}
        <ErrorAlert className="mt-4" error={error} />
        <DialogFooter>
          {success
            ? <Button onClick={() => handleDialog(false)}><Trans>Continue</Trans></Button>
            : <LoadingButton loading={loading} form="user_profile" type="submit" disabled><Trans>Submit</Trans></LoadingButton>
          }
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default UserProfileDialog