import { Table } from "@tanstack/react-table"
import { Button } from "../button"
import { SquareMinus, SquarePlus } from "lucide-react"
import { cn } from "@/lib/utils"
import { Trans } from "@lingui/react/macro"

interface DataTableExpandProps<TData> {
  table: Table<TData>
  className?: string
}

export function DataTableExpand<TData>({
  table,
  className
}: DataTableExpandProps<TData>) {
  const expanded = table.getIsAllRowsExpanded()
  return (
    <Button
      variant="outline"
      className={cn(className, "w-32")}
      onClick={() => table.toggleAllRowsExpanded(!expanded)}
    >
      {expanded === true && <>
        <SquareMinus />
        <Trans>Collapse all</Trans>
      </>}
      {expanded === false && <>
        <SquarePlus />
        <Trans>Expand all</Trans>
      </>}
    </Button>
  )
}