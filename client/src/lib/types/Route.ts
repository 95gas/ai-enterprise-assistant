import { ReactNode } from "react";
import { RouteObject } from "react-router-dom";

export type Route = Omit<RouteObject, "children" | "handle" | "index"> & {
  index?: false
  children?: Route[]
  handle?: {
    getPageName: (data: unknown) => ReactNode
    // getPageIcon?: (data: unknown) => ReactNode
    getPageSidebar?: (data: unknown) => {group: string, icon: ReactNode}
    // revalidatorState type might change with updates to react-router as i'm not able to import the type from react-router-dom
    getPageActions?: (data: unknown, open: boolean, revalidatorState: "idle" | "loading") => ReactNode
  }
}