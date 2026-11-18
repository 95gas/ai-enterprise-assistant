import { PropsWithChildren } from "react";

export function TypographyH1({ id, children }: PropsWithChildren & { id?: string }) {
  return (
    <h1 id={id} className="mt-10 scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl first:mt-0">
      {children}
    </h1>
  )
}