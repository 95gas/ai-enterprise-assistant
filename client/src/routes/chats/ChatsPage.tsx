import { Book, MessageSquareText, MessagesSquare, Plus } from "lucide-react"
import { Suspense, useState } from "react"
import { Route } from "../../lib/types/Route"
import { Await, NavLink, defer, useOutlet } from "react-router-dom"
import { Toggle } from "@/components/ui/toggle"
import { ScrollArea } from "@/components/ui/scroll-area"
import { getChats } from "@/api/chat"
import { Chat } from "@/lib/types/Chat"
import ChatRoute from "./item/ChatPage"
import Navigation from "@/components/ui/custom/navigation"
import ChatsTableCard from "./ChatsTableCard"
import NewChatCard from "./NewChatCard"
import Repeat from "@/components/ui/custom/repeat"
import NewChatDialog from "./NewChatDialog"
import AsyncErrorAlert from "@/components/ui/custom/async-error-alert"
import { Alert } from "@/components/ui/alert"
import { SidebarGroup, SidebarGroupAction, SidebarGroupContent, SidebarGroupLabel, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarMenuSkeleton } from "@/components/ui/sidebar"
import { Trans } from "@lingui/react/macro"

function ChatsPage() {
  const [openDocuments, setOpenDocuments] = useState(false)
  const outlet = useOutlet({ openDocuments, setOpenDocuments })

  return (
    <div className="w-full flex flex-col h-screen">
      <Navigation>
        {outlet ? <Toggle onClick={() => setOpenDocuments(!openDocuments)} variant="outline" pressed={openDocuments}>
          <Book className="h-4 w-4 mr-0 md:mr-2" /> <span className="hidden md:block"><Trans>Documents list</Trans></span>
        </Toggle> : <></>}
      </Navigation>
      <main className="h-full overflow-hidden">
        {outlet ? outlet : (
          <ScrollArea className="h-full">
            <div className="w-full flex justify-center">
              <div className="max-w-[48rem] w-full p-4 grid gap-4">
                <NewChatCard />
                <ChatsTableCard />
              </div>
            </div>
          </ScrollArea>
        )}
      </main>
    </div>
  )
}

function ChatsSidebarError({ open }: { open: boolean }) {
  if (open) {
    return (<AsyncErrorAlert />)
  } else {
    return (<Alert variant="destructive">.</Alert>)
  }
}

const ChatsRoute: Route = {
  path: "chats",
  element: <ChatsPage />,
  children: [
    ChatRoute
  ],
  loader: async () => {
    // the user will be the username given by the login
    const chats = getChats()

    return defer({ chats: chats })
  },
  handle: {
    getPageName: () => <Trans>Chats</Trans>,
    getPageSidebar: () => ({
      group: "workarea",
      icon: <MessageSquareText className='h-4 w-4'/>
    }),
    getPageActions: (data, open, revalidatorState) => {
      const chats = (data as { chats: Chat[] }).chats

      return (
        <SidebarGroup>
          <SidebarGroupLabel><Trans>Recent chats</Trans></SidebarGroupLabel>
          <NewChatDialog>
            <SidebarGroupAction>
              <Plus /> <span className="sr-only"><Trans>New chat</Trans></span>
            </SidebarGroupAction>
          </NewChatDialog>
          <SidebarGroupContent>
            <SidebarMenu>
              <Suspense
                fallback={(
                  <Repeat times={5}>
                    <SidebarMenuSkeleton showIcon />
                  </Repeat>
                )}
              >
                <Await resolve={chats} errorElement={<ChatsSidebarError open={open} />}>
                  {(chats: Chat[]) => {
                    if (revalidatorState === "loading") {
                      return (
                        <Repeat times={5}>
                          <SidebarMenuSkeleton showIcon />
                        </Repeat>
                      )
                    } else {
                      return (chats.slice(0,5).map((chat, index) => (
                        <SidebarMenuItem key={"quick" + index}>
                          <NavLink to={"/chats/" + chat.id}>
                            {({ isActive }) => (
                              <SidebarMenuButton isActive={isActive}>
                                <MessagesSquare /> <span>{chat.name}</span>
                              </SidebarMenuButton>
                            )}
                          </NavLink>
                        </SidebarMenuItem>
                      )))
                    }
                  }}
                </Await>
              </Suspense>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      )
    }
  }
}

export default ChatsRoute