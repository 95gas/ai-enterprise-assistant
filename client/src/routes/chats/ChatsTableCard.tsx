import { deleteChat } from "@/api/chat";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import ConfirmDialog from "@/components/ui/custom/confirm-dialog";
import { DataTable } from "@/components/ui/custom/data-table";
import { DataTablePagination } from "@/components/ui/custom/data-table-pagination";
import { Chat } from "@/lib/types/Chat";
import { ColumnDef, ColumnFiltersState, getCoreRowModel, getFilteredRowModel, getPaginationRowModel, useReactTable } from "@tanstack/react-table";
import { MessagesSquare, Trash2 } from "lucide-react";
import { Suspense, useState } from "react";
import { Await, NavLink, useLoaderData, useRevalidator } from "react-router-dom";
import AsyncErrorAlert from "@/components/ui/custom/async-error-alert";
import { DataTableFilter } from "@/components/ui/custom/data-table-filter";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";

function ChatsTable({ loading, chats }: {
  loading?: boolean,
  chats: Chat[]
}) {
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])

  const columns: ColumnDef<Chat>[] = [{
    accessorKey: "name",
    header: t`Name`,
    filterFn: "includesString",
    cell: ({ row, cell }) => (
      <div className="-m-4 p-2 flex items-center">
        <NavLink to={"/chats/" + row.original.id}>
          <Button
            variant="ghost"
            size="xs"
          >
            <MessagesSquare />
            <div className="truncate max-w-36 md:max-w-80 lg:max-w-96">
              {cell.getValue() as string}
            </div>
          </Button>
        </NavLink>
      </div>
      
    )
  }, {
    id: "actions",
    size: 20,
    header: () => <div className="text-right"><Trans>Actions</Trans></div>,
    cell: ({ row }) => (
      <div className="-m-4 p-2 flex justify-end">
        <ConfirmDialog action={"delete"} objectName={t`the conversation`} onSubmit={() => deleteChat(row.original)}>
          <Button variant="ghost" size="xs" className="float-right">
            <Trash2 />
          </Button>
        </ConfirmDialog>
      </div>
    )
  }]
  
  const table = useReactTable({
    data: chats,
    columns,
    getPaginationRowModel: getPaginationRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getCoreRowModel: getCoreRowModel(),
    onColumnFiltersChange: setColumnFilters,
    state: {
      columnFilters,
    }
  })

  return (
    <div className="grid gap-4">
      <DataTableFilter table={table} column={"name"} columnName={t`Name`} className="bg-card ring-offset-card"/>
      <DataTable loading={loading} columns={columns} table={table} />
      <DataTablePagination table={table} paginationSelectorClassName="bg-card ring-offset-card"/>
    </div>
  )
}

function ChatsTableCard() {
  const revalidator = useRevalidator()
  const data = useLoaderData() as unknown as { chats: Chat[] }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>
          <Trans>Chats</Trans>
        </CardTitle>
        <CardDescription>
          <Trans>List of past conversations</Trans>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Suspense
          fallback={<ChatsTable loading chats={[]} />}
        >
          <Await resolve={data.chats} errorElement={<AsyncErrorAlert />}>
            {(chats: Chat[]) => {
              if (revalidator.state === "loading") {
                return (<ChatsTable loading chats={chats} />)
              } else {
                return (<ChatsTable chats={chats} />)
              }
            }}
          </Await>
        </Suspense>
      </CardContent>
    </Card>
  )
}

export default ChatsTableCard