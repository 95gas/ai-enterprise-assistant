import { useLocation, useNavigate } from "react-router-dom"
import useAuth from "@/lib/hooks/useAuth"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { z } from "zod"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"
import { Input } from "../../components/ui/input"
import { useEffect, useState } from "react"
import LoadingButton from "@/components/ui/custom/loading-button"
import ErrorAlert, { BasicError } from "@/components/ui/custom/error-alert"
import { Trans } from "@lingui/react/macro";

const formSchema = z.object({
  email: z.string().min(1, { message: `E-mail required` }).email({ message: `Invalid e-mail address` }),
  password: z.string().min(1, { message: `Password required` })
})

function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<BasicError>()

  const location = useLocation()
  const from = location.state?.from as string || '/'

  useEffect(() => {
    if (user) {
      navigate(from, { replace: true })
    }
  }, [from, navigate, user])

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      email: "",
      password: ""
    },
  })
  
  async function onSubmit(values: z.infer<typeof formSchema>) {
    setLoading(true)
    const res = await login(values.email, values.password)
    setLoading(false)

    if (!res.ok) {
      const body = await res.json()
      setError({code: res.status, message: body.message})
    } else {
      navigate(from, { replace: true })
    }
  }

  return (
    <div className="flex w-full h-screen justify-center items-center">
      <Card className="w-96 m-4">
        <CardHeader>
          <CardTitle><Trans>Log in to your account</Trans></CardTitle>
          <CardDescription><Trans>Enter your company credentials to log in to ASK.</Trans></CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form id="login" onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel><Trans>E-mail</Trans></FormLabel>
                    <FormControl>
                      <Input type="email" placeholder="email@example.com" className="ring-offset-card bg-card" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel><Trans>Password</Trans></FormLabel>
                    <FormControl>
                      <Input type="password" placeholder="password" className="ring-offset-card bg-card" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </form>
          </Form>
          <ErrorAlert className="mt-4" error={error} />
        </CardContent>
        <CardFooter>
          <LoadingButton loading={loading} className="w-full" form="login" type="submit"><Trans>Login</Trans></LoadingButton>
        </CardFooter>
      </Card>
    </div>
  )
}

export default LoginPage