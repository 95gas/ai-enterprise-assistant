import { PropsWithChildren } from "react";

export function TypographyA({ href, children }: PropsWithChildren & { href?: string }) {
  return (
    <a href={href} target="_blank" className="underline">
      {children}
    </a>
  )
}