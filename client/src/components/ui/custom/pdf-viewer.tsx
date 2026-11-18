import { Card } from "../card"
import { ScrollArea, ScrollBar } from "../scroll-area"
import { Button } from "../button"
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react"
import { Document, Page } from "react-pdf"

import { useEffect, useState } from "react"
import { File } from "node_modules/react-pdf/dist/esm/shared/types"

function PDFViewer({ file, bookmarks }: { file: File, bookmarks?: number[] }) {
  const [numPages, setNumPages] = useState<number>();
  const [pageNumber, setPageNumber] = useState<number>(1);

  function onDocumentLoadSuccess({ numPages }: { numPages: number }): void {
    setNumPages(numPages);
  }

  useEffect(() => {
    if (bookmarks && bookmarks.length > 0) {
      setPageNumber(bookmarks[0])
    }
  }, [bookmarks])

  if (!file?.toString().includes('.pdf')) {
    return (
      <Card className="p-2 flex flex-col items-center overflow-hidden">
        <p>Visualizzazione del documento non supportata</p>
      </Card>
    )
  }

  return (
    <Card className="p-2 flex flex-col items-center overflow-hidden">
      <ScrollArea className="w-full h-full">
        <Document file={file} onLoadSuccess={onDocumentLoadSuccess} className="flex justify-center">
          <Page pageNumber={pageNumber} renderAnnotationLayer={false} renderTextLayer={false}/>
        </Document>
        <ScrollBar orientation="horizontal" />
        <ScrollBar orientation="vertical" />
      </ScrollArea>
      <div className="flex items-center space-x-2 mt-4">
        <Button variant="outline" size="icon" disabled={pageNumber <= 1} onClick={() => setPageNumber(1)}>
          <ChevronsLeft className="h-4 w-4"/>
        </Button>
        <Button variant="outline" size="icon" disabled={pageNumber <= 1} onClick={() => setPageNumber(pageNumber - 1)}>
          <ChevronLeft className="h-4 w-4"/>
        </Button>
        <p className="px-2">Pagina {pageNumber} di {numPages}</p>
        <Button variant="outline" size="icon" disabled={pageNumber >= (numPages ?? 1)} onClick={() => setPageNumber(pageNumber + 1)}>
          <ChevronRight className="h-4 w-4"/>
        </Button>
        <Button variant="outline" size="icon" disabled={pageNumber >= (numPages ?? 1)} onClick={() => setPageNumber(numPages ?? 1)}>
          <ChevronsRight className="h-4 w-4"/>
        </Button>
      </div>
      {bookmarks && (
        <div className="flex items-center flex-wrap mt-2">
          {bookmarks.map(page => (
            <Button variant={"outline"} onClick={() => setPageNumber(page)} className="mr-2 mt-2">
              {page}
            </Button>
          ))}
        </div>
      )}
    </Card>
  )
}

export default PDFViewer