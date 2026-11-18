import { PropsWithChildren } from "react";

export function TypographyOl({ children }: PropsWithChildren) {
  return (
    <ul className="my-6 ml-6 list-decimal [&>li]:mt-2">
      {children}
    </ul>
  )
}