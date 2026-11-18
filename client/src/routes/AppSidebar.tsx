import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from "@/components/ui/sidebar"
import { Route } from "@/lib/types/Route"
import { ReactNode, useEffect, useMemo, useState } from "react"
import AppRoute from "./App"
import { Link, NavLink, useMatches, useNavigate, useRevalidator } from "react-router-dom"
import { AppSummary, getVisibleApps } from "@/api/apps"
import { LayoutGrid } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import useAuth from "@/lib/hooks/useAuth"
import { ChevronsUpDown, Fuel, Languages, Laptop, LogOut, Moon, Sun, SunMoon, User } from "lucide-react"
import { DropdownMenu } from "@radix-ui/react-dropdown-menu"
import { DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuPortal, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import UserProfileDialog from "@/components/sections/UserProfileDialog"
import ConfirmDialog from "@/components/ui/custom/confirm-dialog"
import { useTheme } from "@/lib/hooks/useTheme"
import { Select, Trans } from "@lingui/react/macro"
import { t } from "@lingui/core/macro"
import { dynamicActivate } from "@/i18n"
import TokenUsageDialog from "@/components/sections/TokenUsageDialog"

function getRouteLiks(routes: Route[]): {
  path: string,
  name: ReactNode,
  sidebar: {
    group: string,
    icon: ReactNode
  }
}[] {
  const routesWithLinks = routes.filter(route => route.handle?.getPageSidebar !== undefined && route.path !== undefined)
  const links = routesWithLinks.map(route => ({
    path: route.path!,
    name: route.handle!.getPageName(undefined),
    sidebar: route.handle!.getPageSidebar!(undefined)
  }))
  const childrenLinks = routes.map(route => route.children ? getRouteLiks(route.children) : []).flat(1)

  return [...links, ...childrenLinks]
}

function AppSidebar() {
  const { user, logout } = useAuth()
  const { setTheme } = useTheme()

  const matches = useMatches()
  const revalidator = useRevalidator()
  const navigate = useNavigate()
  const { isMobile } = useSidebar()

  const [logoutOpen, setLogoutOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [usageOpen, setUsageOpen] = useState(false)

  // Phase 59.G — Apps sidebar: fetch vertical-app manifests visible
  // to the caller. The /apps endpoint is gated by visibility_groups
  // + app_specific, so this only renders tiles the user can actually
  // open. Empty list = no Apps section.
  const [apps, setApps] = useState<AppSummary[]>([])
  useEffect(() => {
    let cancelled = false
    getVisibleApps().then((list) => {
      if (!cancelled) setApps(list)
    })
    return () => {
      cancelled = true
    }
  }, [])
  
  const currentPageActions = useMemo(() => {
    const currentMatch = matches
      .slice()
      .reverse()
      .find(match => (match.handle as Route["handle"] | undefined)?.getPageActions)

    const getPageActions = (currentMatch?.handle as Route["handle"] | undefined)?.getPageActions

    if (getPageActions) {
      return getPageActions(currentMatch?.data, true, revalidator.state)
    }

    return undefined
  }, [matches, revalidator.state])

  const links = useMemo(() => {
    const routeLinks = getRouteLiks([AppRoute])
    const groupedLinks = new Map<string, typeof routeLinks>()
    for (const link of routeLinks) {
      const group = groupedLinks.get(link.sidebar.group)
      if (group) {
        group.push(link)
      } else {
        groupedLinks.set(link.sidebar.group, [link])
      }

    }

    return groupedLinks
  }, [])

  return(
    <Sidebar>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <Link to="/">
              <SidebarMenuButton size={"lg"}>
                <img src={"/logo.svg"} alt={import.meta.env.VITE_NAME} className="h-8"/>
              </SidebarMenuButton>
            </Link>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        {[...links.keys()].map(key => (
          <SidebarGroup key={"navgroup" + key}>
            <SidebarGroupLabel>
              <Select
                value={key}
                _workarea={"Work Area"}
                _information={"Information"}
                other={"Unknown"}
              />
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {links.get(key)?.map((route, index) => (
                  <SidebarMenuItem key={"nav" + index}>
                    <NavLink to={route.path} className={({ isActive }) => isActive && route.path !== "ask" ? "pointer-events-none" : ""}>
                      {({ isActive }) => (
                        <SidebarMenuButton isActive={isActive}>
                          {route.sidebar.icon} <span>{route.name}</span>
                        </SidebarMenuButton>
                      )}
                    </NavLink>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
        {/* Phase 59.G — Apps sidebar group. Each tile opens a chat
            session bound to the app's workflow via a search param;
            AskPage reads it on mount + sets the workflow state. */}
        {apps.length > 0 && (
          <SidebarGroup key="apps">
            <SidebarGroupLabel>
              <Trans>Apps</Trans>
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {apps.map((app) => (
                  <SidebarMenuItem key={"app-" + app.id}>
                    <SidebarMenuButton
                      onClick={() => navigate(`/ask?app=${encodeURIComponent(app.workflow)}`)}
                      title={app.description}
                    >
                      <LayoutGrid className="size-4" />
                      <span>{app.name}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
        {currentPageActions}
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton size={"lg"}>
                  <Avatar>
                    <AvatarImage src="" alt="@you" />
                    <AvatarFallback>
                      <User className="h-5 w-5"/>
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold">{user?.name}</span>
                    <span className="truncate text-xs">{user?.email}</span>
                    {/* Phase 59.G — surface the user's visibility
                        groups so a user can self-diagnose "why
                        don't I see app X?" — the orchestrator + the
                        apps list both filter by these. */}
                    {user?.groups && user.groups.length > 0 && (
                      <span
                        className="truncate text-[10px] opacity-60"
                        title={user.groups.join(", ")}
                      >
                        {user.groups.join(", ")}
                      </span>
                    )}
                  </div>
                  <ChevronsUpDown className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
                side={isMobile ? "top" : "right"}
                align="end"
                sideOffset={4}
              >
                <DropdownMenuLabel>
                  <Trans>Settings</Trans>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <SunMoon className="h-4 w-4 mr-2"/>
                    <Trans>Theme</Trans>
                  </DropdownMenuSubTrigger>
                  <DropdownMenuPortal>
                    <DropdownMenuSubContent>
                      <DropdownMenuItem onClick={() => setTheme('system')}>
                        <Laptop className="h-4 w-4 mr-2"/>
                        <Trans>System theme</Trans>
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setTheme('light')}>
                        <Sun className="h-4 w-4 mr-2"/>
                        <Trans>Light theme</Trans>
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setTheme('dark')}>
                        <Moon className="h-4 w-4 mr-2"/>
                        <Trans>Dark theme</Trans>
                      </DropdownMenuItem>
                    </DropdownMenuSubContent>
                  </DropdownMenuPortal>
                </DropdownMenuSub>
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <Languages className="h-4 w-4 mr-2"/>
                    <Trans>Language</Trans>
                  </DropdownMenuSubTrigger>
                  <DropdownMenuPortal>
                    <DropdownMenuSubContent>
                      <DropdownMenuItem onClick={() => dynamicActivate('it')}>
                        Italiano
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => dynamicActivate('en')}>
                        English
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => dynamicActivate('zh')}>
                        中文
                      </DropdownMenuItem>
                    </DropdownMenuSubContent>
                  </DropdownMenuPortal>
                </DropdownMenuSub>
                <UserProfileDialog open={profileOpen} onOpenChange={setProfileOpen}>
                  <DropdownMenuItem onClick={(e) => { setProfileOpen(!profileOpen); e.preventDefault() }}>
                    <User className="mr-2 h-4 w-4" />
                    <span><Trans>User Data</Trans></span>
                  </DropdownMenuItem>
                </UserProfileDialog>
                <TokenUsageDialog open={usageOpen} onOpenChange={setUsageOpen}>
                  <DropdownMenuItem onClick={(e) => { setUsageOpen(!profileOpen); e.preventDefault() }}>
                    <Fuel className="mr-2 h-4 w-4" />
                    <span><Trans>Tokens Consumption</Trans></span>
                  </DropdownMenuItem>
                </TokenUsageDialog>
                <DropdownMenuSeparator />
                <ConfirmDialog action={"logout"} objectName={user?.name ?? t`user`} onSubmit={logout} open={logoutOpen} onOpenChange={setLogoutOpen}>
                  <DropdownMenuItem onClick={(e) => { setLogoutOpen(!logoutOpen); e.preventDefault() }}>
                    <LogOut className="mr-2 h-4 w-4" />
                    <span><Trans>Logout</Trans></span>
                  </DropdownMenuItem>
                </ConfirmDialog>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar