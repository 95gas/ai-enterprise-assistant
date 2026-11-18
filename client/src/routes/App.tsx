import { Outlet, useLocation, useNavigate } from "react-router-dom"
import ProtectedRoute from "@/components/providers/ProtectedRoute"
import { Route } from "@/lib/types/Route"
import ChatsRoute from "./chats/ChatsPage"
import NotFoundPage from "./NotFoundPage"
import { useEffect } from "react"
import { Toaster } from "@/components/ui/sonner"
import DocumentRoute from "./documents/DocumentPage"
import AskRoute from "./ask/AskPage"
import AppSidebar from "./AppSidebar"
import ManualRoute from "./pages/ManualPage"
import PrivacyRoute from "./pages/PrivacyPage"
import ChangelogsRoute from "./pages/ChangelogsPage"
import SettingsRoute from "./settings/SettingsPage"


function App() {
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    if (location.pathname === "/") {
      navigate('/ask', { replace: true })
    }
  }, [navigate, location.pathname])

  return (
    <>
      <AppSidebar/>
      <div className="w-full">
        <Outlet key={location.key}/>
        <Toaster />
      </div>
    </>
  )
}

const AppRoute: Route = {
  path: "",
  element: (
    <ProtectedRoute>
      <App/>
    </ProtectedRoute>
  ),
  errorElement: <NotFoundPage/>,
  children: [
    AskRoute,
    ChatsRoute,
    DocumentRoute,
    SettingsRoute,
    ManualRoute,
    PrivacyRoute,
    ChangelogsRoute
  ]
}

export default AppRoute