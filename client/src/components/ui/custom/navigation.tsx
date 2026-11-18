import { Breadcrumb, BreadcrumbEllipsis, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb"
import { Route } from "@/lib/types/Route"
import { Fragment, PropsWithChildren, useMemo } from "react"
import { Link, useMatches } from "react-router-dom"
import { Separator } from "../separator"
import { SidebarTrigger, useSidebar } from "../sidebar"
import { DropdownMenu } from "@radix-ui/react-dropdown-menu"
import { DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../dropdown-menu"

function Navigation({ children }: PropsWithChildren) {
  const { isMobile } = useSidebar()
  const matches = useMatches()

  const breadcrumbs = useMemo(() => {
    return matches
      .filter(match => match.handle)
      .map(match => ({
        path: match.pathname,
        name: (match.handle as Route["handle"])!.getPageName(match.data)
      }))

  }, [matches])

  return (
    <header className="flex h-16 items-center justify-between gap-2 border-b">
      <div className="flex items-center gap-2 px-4">
        <SidebarTrigger/>
        <Separator orientation={"vertical"} className="mr-2 h-4"/>
        <Breadcrumb >
          <BreadcrumbList>
            {isMobile && breadcrumbs.length > 1 ? (
              <>
                <DropdownMenu>
                  <DropdownMenuTrigger>
                    <BreadcrumbEllipsis className="h-4 w-4" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent side={"bottom"} align={"start"}>
                    {breadcrumbs.slice(0, -1).map((breadcrumb) => (
                      <DropdownMenuItem key={breadcrumb.path}>
                        <Link to={breadcrumb.path}> {breadcrumb.name}</Link>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
                <BreadcrumbSeparator/>
                <BreadcrumbPage className="max-w-20 truncate md:max-w-none">
                  {breadcrumbs.at(-1)?.name}
                </BreadcrumbPage>
              </>
            ) : (
              breadcrumbs.map((breadcrumb, index) => (
                <Fragment key={breadcrumb.path}>
                  <BreadcrumbItem>
                    {index !== (breadcrumbs.length - 1) ? (
                      <BreadcrumbLink asChild>
                        <Link to={breadcrumb.path}> {breadcrumb.name}</Link>
                      </BreadcrumbLink>
                    ) : (
                      <BreadcrumbPage className="max-w-28 truncate md:max-w-none">
                        {breadcrumb.name}
                      </BreadcrumbPage>
                    )}
                  </BreadcrumbItem>
                  {index !== (breadcrumbs.length - 1) && <BreadcrumbSeparator/>}
                </Fragment>
              ))
            )}
          </BreadcrumbList>
        </Breadcrumb>
      </div>
      <div className="flex items-center gap-2 px-4">
        {children}
      </div>
    </header>
  )
}

export default Navigation