import { deleteDocument } from "@/api/document"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import ConfirmDialog from "@/components/ui/custom/confirm-dialog"
import { DataTable } from "@/components/ui/custom/data-table"
import { getDocuments } from "@/api/document"
import { DataTablePagination } from "@/components/ui/custom/data-table-pagination"
import { Document, FileTree } from "@/lib/types/Document"
import { ColumnDef, ColumnFiltersState, ExpandedState, getCoreRowModel, getExpandedRowModel, getFilteredRowModel, getPaginationRowModel, getSortedRowModel, SortingState, useReactTable } from "@tanstack/react-table"
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight, ExternalLink, FileText, Folder, FolderOpen, Trash2 } from "lucide-react"
import { Suspense, useMemo, useState, useEffect } from "react"
import { Await, useLoaderData, useRevalidator } from "react-router-dom"
import AsyncErrorAlert from "@/components/ui/custom/async-error-alert"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import DocumentViewer from "@/components/ui/custom/document-viewer"
import { DataTableFilter } from "@/components/ui/custom/data-table-filter"
import useAuth from "@/lib/hooks/useAuth"
import { t } from "@lingui/core/macro"
import { Trans } from "@lingui/react/macro"
import useSocket from "@/lib/hooks/useSocket"
import { buildFileTree } from "@/lib/utils"
import { DataTableExpand } from "@/components/ui/custom/data-table-expand"

function DocumentTable({ loading, documents }: {
  loading?: boolean,
  documents: Document[]
}) {
  const { user } = useAuth()
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [expanded, setExpanded] = useState<ExpandedState>({})
  const [columnSorting, setColumnSorting] = useState<SortingState>([{id: "name", desc: false}])
  
  const elements = useMemo(() => buildFileTree(documents), [documents])

  const columns: ColumnDef<FileTree>[] = useMemo(() => {
    const main: ColumnDef<FileTree>[] = [{
      accessorKey: "name",
      header: ({ column }) => {
        const sorted = column.getIsSorted()
        return (
          <div className="-m-4 p-2 flex items-center">
            <Button
              variant="ghost"
              size="xs"
              onClick={() => sorted === "desc" ?  column.clearSorting() : column.toggleSorting(sorted === "asc")}
            >
              {sorted === false && <ArrowUpDown className="h-4 w-4" />}
              {sorted === "asc" && <ArrowUp className="h-4 w-4" />}
              {sorted === "desc" && <ArrowDown className="h-4 w-4" />}
              <Trans>Name</Trans>
            </Button>
          </div>
        )
      },
      cell: ({ row }) => {
        const type = row.original.type
        const depth = row.original.depth
        
        const expanded = row.getIsExpanded()
        
        if (type === "document") {
          const document = row.original.original

          return (
            <div className="-m-4 p-2 flex items-center">
              <Dialog>
                <DialogTrigger asChild>
                  <Button
                    variant="ghost"
                    size="xs"
                    style={{
                      marginLeft: 1.5 * depth + "rem"
                    }}
                  >
                    <FileText className="h-4 w-4" />
                    <span className="truncate max-w-36 md:max-w-80 lg:max-w-96">
                      {row.original.name}
                    </span>
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-[42rem] max-h-[58rem] h-full">
                  <DialogHeader>
                    <DialogTitle className="truncate max-w-[38rem]">
                      <Trans>Document view</Trans>
                    </DialogTitle>
                    <DialogDescription className="truncate max-w-[38rem]">
                      <Trans>Viewing document {row.original.name}</Trans>
                    </DialogDescription>
                  </DialogHeader>
                  <div className="flex flex-col overflow-hidden" >
                    <DocumentViewer s3Bucket={document.s3_bucket} s3Path={document.s3_path} filename={document.filename}/>
                  </div>
                </DialogContent>
              </Dialog>
            </div>
          )
        }

        if (type === "folder") {
          return (
            <div className="-m-4 p-2 flex items-center">
              <Button
                variant="ghost"
                size="xs"
                onClick={row.getToggleExpandedHandler()}
                style={{
                  marginLeft: 1.5 * depth + "rem"
                }}
              >
                {expanded === true && <><ChevronDown /> <FolderOpen /></>}
                {expanded === false && <><ChevronRight /><Folder /></>}
                <span className="truncate max-w-36 md:max-w-80 lg:max-w-96">
                  {row.original.name}
                </span>
              </Button>
            </div>
          )
        }
      },
      filterFn: (row, columnId, filterValue) => {
        const value = String(row.getValue(columnId) ?? '').toLowerCase()
        const filter = String(filterValue).toLowerCase()

        if (value.includes(filter)) {
          return true
        }

        const parents = row.getParentRows()
        for (const parent of parents) {
          const value = String(parent.getValue(columnId) ?? '').toLowerCase()

          if (value.includes(filter)) {
            return true
          }
        }

        return false
      },
      sortingFn: (rowA, rowB) => {
        const typeA = rowA.original.type
        const typeB = rowB.original.type
        const nameA = rowA.original.name.toLowerCase()
        const nameB = rowB.original.name.toLowerCase()

        if (typeA === 'folder' && typeB !== 'folder') return -1
        if (typeA !== 'folder' && typeB === 'folder') return 1

        return nameA.localeCompare(nameB)
      }
    }, {
      id: "date",
      header: t`Date`,
      cell: ({ row }) => {
        return row.original.original?.upload_datetime
      }
    }, {
      id: "token",
      header: t`Token`,
      cell: ({ row }) => {
        return row.original.original?.totalTokens
      }
    }, {
      id: "uri",
      header: t`Link`,
      cell: ({ row }) => {
        const document = row.original.original

        if (row.original.type !== "document" || !document?.og_uri) {
          return null
        }

        return (
          <Button variant="ghost" size="xs" asChild>
            <a
              href={document.og_uri}
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          </Button>
        )
      }
    }]


    const actions: ColumnDef<FileTree> = {
      id: "actions",
      header: () => <div className="text-right"><Trans>Actions</Trans></div>,
      cell: ({ row }) => {
        const type = row.original.type

        if (type === "folder") {
          return ""
        }

        if (type === "document") {
          const document = row.original.original

          const canDelete = (user?.permissions?.upload_common && document.s3_bucket === "shared") || (user?.permissions?.upload_private && document.s3_bucket === "users")
          return (
            <div className="-m-4 p-2 flex justify-end">
              <ConfirmDialog action={"delete"} objectName={`the document`} onSubmit={() => deleteDocument(document)}>
                <Button variant="ghost" size="xs" disabled={!canDelete}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </ConfirmDialog>
            </div>
          )
        }
      }
    }

    // if (user?.permissions?.upload_common) {
      return [...main, actions]
    // }

    return main
  }, [user])
  
  const table = useReactTable({
    data: elements,
    columns: columns,
    paginateExpandedRows: true,
    filterFromLeafRows: true,
    getSubRows: (row) => row.childrens,
    getPaginationRowModel: getPaginationRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getCoreRowModel: getCoreRowModel(),
    onColumnFiltersChange: setColumnFilters,
    onSortingChange: setColumnSorting,
    onExpandedChange: setExpanded,
    state: {
      sorting: columnSorting,
      columnFilters,
      expanded
    }
  })

  return (
    <div className="grid gap-4 w-full">
      <div className="flex gap-4">
        <DataTableFilter table={table} column={"name"} columnName={t`Name`} className="bg-card ring-offset-card"/>
        <DataTableExpand table={table} className="flex-none"/>
      </div>
      <DataTable loading={loading} columns={columns} table={table}/>
      <DataTablePagination table={table} paginationSelectorClassName="bg-card ring-offset-card"/>
    </div>
  )
}

function DocumentsTableCard() {
  const revalidator = useRevalidator()
  const socket = useSocket()
  const data = useLoaderData() as unknown as { documents: Promise<Document[]> }

  // Initialize state with the promise from the loader
  const [documentsPromise, setDocumentsPromise] = useState<Promise<Document[]>>(data.documents)

  // this is needed to refresh the component after the load of the page such as when delete operation happens
  useEffect(() => {
    setDocumentsPromise(data.documents)
  }, [data.documents])

  // this is refreshing the component as something on the socket comes
  useEffect(() => {
    if (!socket) return;
    const eventName = "current_doc_processing"

    const handleEvent = () => {
      setDocumentsPromise(getDocuments())
    }

    socket.on(eventName, handleEvent)

    return () => {
        socket.off(eventName, handleEvent)
    }
  }, [socket])
  
  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>
          <Trans>Uploaded documents</Trans>
        </CardTitle>
        <CardDescription>
          <Trans>List of uploaded documents</Trans>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Suspense
          fallback={<DocumentTable loading documents={[]}/>}
        >
          <Await resolve={documentsPromise} errorElement={<AsyncErrorAlert/>}>
          {(documents: Document[]) => {
              if (revalidator.state === "loading") {
                return (<DocumentTable loading documents={documents}/>)
              } else {
                return (
                  <DocumentTable documents={documents}/>
                )
              }
            }}
          </Await>
        </Suspense>
      </CardContent>
    </Card>
  )
}

export default DocumentsTableCard