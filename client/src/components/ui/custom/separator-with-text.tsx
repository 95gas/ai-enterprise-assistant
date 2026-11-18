import React from "react";
import { Separator } from "../separator";
import { cn } from "@/lib/utils";

type SeparatorWithTextProps = {
  text: string
} & React.ComponentProps<typeof Separator>

function SeparatorWithText(props: SeparatorWithTextProps) {
  return (
    <div className={cn(
      props.className
    )}>
      <div className="flex justify-center items-center text-xs uppercase">
        <Separator className="w-auto flex-1"/>
        <span className="px-2 text-muted-foreground">{props.text}</span>
        <Separator className="w-auto flex-1"/>
      </div>
    </div>
  )
}

export default SeparatorWithText