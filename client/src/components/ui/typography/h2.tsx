import { PropsWithChildren } from "react";

export function TypographyH2({ id, children }: PropsWithChildren & { id?: string }) {
  return (
    <h2 id={id} className="mt-10 scroll-m-20 border-b pb-2 text-3xl font-semibold tracking-tight first:mt-0">
      {children}
    </h2>
  )
}