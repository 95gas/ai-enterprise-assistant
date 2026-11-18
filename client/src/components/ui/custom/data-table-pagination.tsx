import {
    ChevronLeft,
    ChevronRight,
    ChevronsLeft,
    ChevronsRight,
  } from "lucide-react"
  import { Table } from "@tanstack/react-table"
  
  import { Button } from "../button"
  import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
  } from "../select"
import { cn } from "@/lib/utils"
import { Plural, Trans } from "@lingui/react/macro"
  
interface DataTablePaginationProps<TData> {
  table: Table<TData>
  hidePageSizeSelector?: boolean
  paginationSelectorClassName?: string
}

export function DataTablePagination<TData>({
  table,
  hidePageSizeSelector,
  paginationSelectorClassName
}: DataTablePaginationProps<TData>) {
  return (
    <div className="flex items-center justify-between px-2">
      <div className={"flex items-center w-full justify-between"}>
        {!hidePageSizeSelector && (
          <div className="hidden sm:flex items-center space-x-2">
            <p className="text-sm font-medium text-muted-foreground"><Trans>Rows</Trans></p>
            <Select
              value={`${table.getState().pagination.pageSize}`}
              onValueChange={(value) => {
                table.setPageSize(Number(value))
              }}
            >
              <SelectTrigger className={cn("h-8 w-[70px]", paginationSelectorClassName)}>
                <SelectValue placeholder={table.getState().pagination.pageSize} />
              </SelectTrigger>
              <SelectContent side="top">
                {[10, 20, 30, 40, 50].map((pageSize) => (
                  <SelectItem key={pageSize} value={`${pageSize}`}>
                    {pageSize}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="flex items-center justify-center text-sm font-medium text-muted-foreground">
          <Trans>
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}{" "}
            <Plural
              value={table.getSelectedRowModel().flatRows.length}
              _0=""
              one="(# selected)"
              other="(# selected)"
            />
          </Trans>
        </div>
        <div className="flex items-center space-x-2">
          <Button
            variant="outline"
            className="hidden h-8 w-8 p-0 lg:flex"
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
          >
            <span className="sr-only"><Trans>Go to first page</Trans></span>
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            className="h-8 w-8 p-0"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            <span className="sr-only"><Trans>Go to previous page</Trans></span>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            className="h-8 w-8 p-0"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            <span className="sr-only"><Trans>Go to next page</Trans></span>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            className="hidden h-8 w-8 p-0 lg:flex"
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
          >
            <span className="sr-only"><Trans>Go to last page</Trans></span>
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
  