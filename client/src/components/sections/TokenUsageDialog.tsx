import { PropsWithChildren, useEffect, useState } from "react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog"
import { Trans, useLingui } from "@lingui/react/macro"
import { getModels } from "@/api/model"
import { Model } from "@/lib/types/Model"
import { type ColumnDef, getCoreRowModel, useReactTable } from "@tanstack/react-table"
import { DataTable } from "../ui/custom/data-table"
import { Progress } from "../ui/progress"
import useAuth from "@/lib/hooks/useAuth"
import { t } from "@lingui/core/macro"

function TokenUsageDialog({ children, open, onOpenChange }: PropsWithChildren & {
  open?: boolean,
  onOpenChange?: (open: boolean) => void
}) {
  const { i18n } = useLingui()
  const { user } = useAuth()
  const [usage, setUsage] = useState<Model[]>([])
  const totalUsage = usage.reduce((a, b) => a + b.tot_tokens_timeframe, 0)
  const totalUsagePercentage = Math.min(Math.ceil((totalUsage / user!.tot_token_limit) * 100), 100)

  useEffect(() => {
    getModels().then(res => setUsage(res))
  }, []) 

  const columns: ColumnDef<Model>[] = [{
    accessorKey: "model",
    header: t`Model`
  }, {
    accessorKey: "provider",
    header: t`Provider`,
  }, {
    accessorKey: "limit_reset_period",
    header: t`Tokens reset period`
  }, {
    accessorKey: "resetting_datetime",
    header: t`Next reset`,
    cell: ({ cell }) => {
      const value = cell.getValue() as string
      const date = new Date(value)
      
      return i18n.date(date, {
        dateStyle: "long",
        timeStyle: "short"
      })
    }
  }, {
    id: "tokens_usage",
    header: t`Tokens usage`,
    cell: ({ row }) => {
      const model = row.original
      const percentage = Math.min(Math.ceil((model.tot_tokens_timeframe / model.tokens_limit) * 100), 100)
      return (
        <div className="w-56 space-y-1">
          <Progress value={percentage} className="h-2"/>
          <div className="flex justify-between text-xs text-muted-foreground">
            <Trans>
              <span>{model.tot_tokens_timeframe} of {model.tokens_limit} tokens</span>
              <span>{percentage}%</span>
            </Trans>
          </div>
        </div>
      )
    }
  }]

  const table = useReactTable({
    data: usage,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent className="max-w-fit">
        <DialogHeader>
          <DialogTitle><Trans>Tokens Consumption</Trans></DialogTitle>
          <DialogDescription><Trans>Details on the usage of tokens</Trans></DialogDescription>
        </DialogHeader>
        <div><Trans>Account tokens usage</Trans></div>
        <div className="w-full space-y-1 border p-4 rounded-md">
          <Progress value={totalUsagePercentage} className="h-2"/>
          <div className="flex justify-between text-xs text-muted-foreground">
            <Trans>
              <span>{totalUsage} of {user?.tot_token_limit} tokens</span>
              <span>{totalUsagePercentage}%</span>
            </Trans>
          </div>
        </div>
        <div><Trans>Models tokens usage</Trans></div>
        <DataTable loading={false} columns={columns} table={table} />
      </DialogContent>
    </Dialog>
  )
}

export default TokenUsageDialog