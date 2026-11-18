import Navigation from "@/components/ui/custom/navigation"
import { Route } from "@/lib/types/Route"
import { Folder } from "lucide-react"
import { getDocuments } from "@/api/document"
import { defer } from "react-router-dom"
import UploadDocumentsCard from "./UploadDocumentsCard"
import { ScrollArea } from "@/components/ui/scroll-area"
import DocumentsTableCard from "./DocumentsTableCard"
import useAuth from "@/lib/hooks/useAuth"
import { Trans } from "@lingui/react/macro"

function DocumentPage() {
  const { user } = useAuth()

  return (
    <div className="w-full flex flex-col h-screen">
      <Navigation />
      <main className="h-full overflow-hidden">
        <ScrollArea className="h-full">
          <div className="w-full flex justify-center">
            <div className="max-w-[48rem] w-full p-4 grid gap-4">
              {(user?.permissions?.upload_common || user?.permissions?.upload_private) && <UploadDocumentsCard />}
              <DocumentsTableCard />
            </div>
          </div>
        </ScrollArea>
      </main>
    </div>
  )
}

const DocumentRoute: Route = {
  path: "documents",
  element: <DocumentPage/>,
  loader: async () => {
    const documents = getDocuments()

    return defer({ documents: documents })
  },
  handle: {
    getPageName: () => <Trans>Documents</Trans>,
    getPageSidebar: () => ({
      group: "workarea",
      icon: <Folder className='h-4 w-4'/>
    }),
  }
}

export default DocumentRoute