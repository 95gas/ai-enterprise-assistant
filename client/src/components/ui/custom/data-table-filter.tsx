import { Table } from "@tanstack/react-table"
import { Input } from "../input"
import { cn } from "@/lib/utils"
import { t } from "@lingui/core/macro"

interface DataTableFilterProps<TData> {
  table: Table<TData>
  column: string
  columnName: string
  className?: string
}

export function DataTableFilter<TData>({
  table,
  column,
  columnName,
  className
}: DataTableFilterProps<TData>) {
  return (
    <div className="flex items-center flex-1">
      <Input
        className={cn(className)}
        placeholder={t`Search by ${columnName}...`}
        value={(table.getColumn(column)?.getFilterValue() as string) ?? ""}
        onChange={(event) =>
          table.getColumn(column)?.setFilterValue(event.target.value)
        }
      />
    </div>
  )
}