import { PropsWithChildren } from "react";

export function TypographyH3({ children }: PropsWithChildren) {
  return (
    <h3 className="mt-8 scroll-m-20 text-2xl font-semibold tracking-tight">
      {children}
    </h3>
  )
}