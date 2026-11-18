import { PropsWithChildren, useMemo, useState } from "react";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog";
import { Document, FileTree } from "@/lib/types/Document";
import { ColumnDef, ColumnFiltersState, ExpandedState, getCoreRowModel, getExpandedRowModel, getFilteredRowModel, getPaginationRowModel, getSortedRowModel, OnChangeFn, RowSelectionState, SortingState, useReactTable } from "@tanstack/react-table";
import { DataTable } from "../ui/custom/data-table";
import { DataTablePagination } from "../ui/custom/data-table-pagination";
import { DataTableFilter } from "../ui/custom/data-table-filter";
import { Checkbox } from "../ui/checkbox";
import { Button } from "../ui/button";
import { ScrollArea } from "../ui/scroll-area";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Model } from "@/lib/types/Model";
import { buildFileTree } from "@/lib/utils";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";
import { DataTableExpand } from "../ui/custom/data-table-expand";

function DocumentTable({ elements, loading, showTokens, overMaxDocuments, selectedModel, selectedDocuments, setSelectedDocuments, rowSelection, setRowSelection }:  {
  elements: FileTree[]
  loading?: boolean
  showTokens?: boolean
  overMaxDocuments: boolean
  selectedModel: Model | undefined
  selectedDocuments: Document[]
  setSelectedDocuments: (documents: Document[]) => void
  rowSelection: RowSelectionState
  setRowSelection: OnChangeFn<RowSelectionState>
}) {
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [expanded, setExpanded] = useState<ExpandedState>({})
  const [columnSorting, setColumnSorting] = useState<SortingState>([{id: "name", desc: false}])

  const columns: ColumnDef<FileTree>[] = useMemo(() => {
    const main: ColumnDef<FileTree>[] = [{
      id: "select",
      size: 32,
      header: ({ table }) => (
        <Checkbox
          checked={
            table.getIsAllRowsSelected() ||
            (table.getIsSomeRowsSelected() && "indeterminate")
          }
          onCheckedChange={(value) => table.toggleAllRowsSelected(!!value)}
        />
      ),
      cell: ({ row }) => {
        const type = row.original.type

        if (type === "document") {
          return (
            <div className="py-2 pl-4 -my-4 -ml-4">
              <Checkbox
                checked={row.getIsSelected()}
                onCheckedChange={(value) => row.toggleSelected(!!value) }
              />
            </div>
          )
        }

        if (type === "folder") {
          return (
            <div className="py-2 pl-4 -my-4 -ml-4">
              <Checkbox
                checked={
                  row.getIsSelected() ||
                  (row.getIsSomeSelected() && "indeterminate")
                }
                onCheckedChange={(value) => row.toggleSelected(!!value) }
              />
            </div>
          )
        }
      }
    }, {
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
        const name = row.original.name
        const expanded = row.getIsExpanded()
        
        if (type === "document") {
          return (
            <div className="-m-4 p-2 flex items-center">
              <Button
                variant="ghost"
                size="xs"
                onClick={() => row.toggleSelected(!row.getIsSelected())}
                style={{
                  marginLeft: 1.5 * depth + "rem"
                }}
              >
                <FileText className="h-4 w-4" />
                <span className="truncate max-w-36 md:max-w-80 lg:max-w-96">
                  {name}
                </span>
              </Button>
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
                  {name}
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
      id: "totalTokens",
      header: t`Tokens`,
      cell: ({ row }) => {
        const type = row.original.type

        if (type === "document") {
          return row.original.original!.totalTokens
        }

        if (type === "folder") {
          return ""
        }
      }
    }]

    return main
  }, [])

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
    onRowSelectionChange: (updater) => {
      const newSelection = typeof updater === 'function' ? updater(rowSelection) : updater
      const syncedSelection = { ...newSelection }
      
      // bubble children selection to parent
      const rows = [...table.getRowModel().rows].reverse()
      for (const row of rows) {
        if (row.getCanSelect() && row.subRows?.length > 0) {
          const allChildrenSelected = row.subRows.every(sub => !!syncedSelection[sub.id])
          
          if (allChildrenSelected) {
            syncedSelection[row.id] = true
          } else {
            delete syncedSelection[row.id]
          }
        }
      }

      // get original documents selection
      // The `.filter` MUST use a type predicate (`is Document`) so TS
      // narrows the array element type from `Document | undefined` to
      // `Document` — without the predicate the inferred type stays
      // `(Document | undefined)[]` and the `setSelectedDocuments`
      // call below fails strict-mode type-check.
      const selectedDocuments = Object.keys(syncedSelection).map(rowId => {
        return table.getRow(rowId).original.original
      }).filter((document): document is Document => document !== undefined)

      setRowSelection(syncedSelection)
      setSelectedDocuments(selectedDocuments)
    },
    onExpandedChange: setExpanded,
    state: {
      sorting: columnSorting,
      columnFilters,
      rowSelection: rowSelection,
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
      <DataTablePagination table={table} hidePageSizeSelector/>
      {selectedDocuments.length > 0 ? (
        <ScrollArea className="max-h-36">
          {showTokens && <p><Trans>Total selected documents tokens: {selectedDocuments.reduce((a, b) => a + b.totalTokens, 0)} out of {Math.floor((selectedModel?.context_window ?? 0) / 4)}</Trans></p>}
          <p><Trans>Selected documents:</Trans></p>
          <ul className="my-2 ml-6 list-disc">
            {selectedDocuments.map(s => (
              <li key={"doc" + s.s3_path}>
                <p className="text-sm text-muted-foreground truncate max-w-36 md:max-w-80 lg:max-w-96">
                  {s.filename}
                </p>
              </li>
            ))}
          </ul>
        </ScrollArea>
      ) : (
        <ScrollArea className="max-h-36">
          {showTokens ? (
            <p><Trans>No selected documents, focus mode requires at least one selected document</Trans></p>
          ) : (
            <p><Trans>No selected documents, the search will consider all documents available</Trans></p>
          )}
          {overMaxDocuments && (
            <p className="text-destructive "><Trans>Selected documents are over the maximum allowed length</Trans></p>
          )}
        </ScrollArea>
      )}
    </div>
  )
}

// TODO: rename showTokens to focus
function DocumentSelectorDialog({ children, documents, showTokens, overMaxDocuments, selectedModel, selectedDocuments, setSelectedDocuments }: PropsWithChildren & {
  documents: Document[]
  showTokens?: boolean
  overMaxDocuments: boolean
  selectedModel: Model | undefined
  selectedDocuments: Document[]
  setSelectedDocuments: (documents: Document[]) => void
}) {
  
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const elements = useMemo(() => buildFileTree(documents), [documents])

  return (
    <Dialog>
      <DialogTrigger asChild>
        {children}
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle><Trans>Select documents</Trans></DialogTitle>
          <DialogDescription><Trans>Select documents to work on</Trans></DialogDescription>
        </DialogHeader>
        <DocumentTable elements={elements} showTokens={showTokens} overMaxDocuments={overMaxDocuments} selectedModel={selectedModel} selectedDocuments={selectedDocuments} setSelectedDocuments={setSelectedDocuments} rowSelection={rowSelection} setRowSelection={setRowSelection} />
        <DialogFooter>
          <DialogClose disabled={(showTokens && selectedDocuments.length === 0) || overMaxDocuments} asChild>
            <Button><Trans>Continue</Trans></Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default DocumentSelectorDialog