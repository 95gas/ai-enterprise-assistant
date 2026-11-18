import * as React from "react"
import { Check, ChevronDown} from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { t } from "@lingui/core/macro"
import { Trans } from "@lingui/react/macro"

type BasicItem = {
  id: string,
  label: string
  disabled?: boolean
}

type MultiSelectProps<T extends BasicItem> = {
  items: T[]
  objectName: string,
  values?: T[]
  disabled?: boolean
  onValuesChange?: (values: T[]) => void
  searchable?: boolean
  buttonClassName?: string
  popoverClassName?: string
}

export function MultiSelect<T extends BasicItem>({items, objectName, values, disabled, onValuesChange, searchable, buttonClassName, popoverClassName}: MultiSelectProps<T>) {
  const [open, setOpen] = React.useState(false)
  const [selected, setSelected] = React.useState<T[]>(values ?? [])

  React.useEffect(() => {
    if (values) {
      setSelected(values)
    }
  }, [values])

  const updateSelected = (item: T) => {
    const newSelected = [...selected]

    const selectedIndex = selected.findIndex(s => s.id === item.id)
    if (selectedIndex !== -1) {
      newSelected.splice(selectedIndex, 1)
    } else {
      newSelected.push(item)
    }

    setSelected(newSelected)

    if (onValuesChange) {
      onValuesChange(newSelected)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen} modal={true}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "justify-between hover:bg-transparent",
            (open && !disabled && "ring-offset-background ring-2 ring-ring ring-offset-2"),
            buttonClassName
          )}
        >
          <div className="w-full flex text-start">
            {selected.length > 0
              ? <div className={"w-1 flex-1 truncate" + (disabled ? " opacity-50" : "")}>{selected.map(s => s.label).join(", ")}</div>
              : <div className="w-1 flex-1 text-muted-foreground truncate"><Trans>Select {objectName}</Trans></div>
            }
          </div>
          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className={cn(
        "p-0",
        popoverClassName
      )}>
        <Command>
          {searchable && <CommandInput placeholder={t`Search by ${objectName}...`} />}
          <CommandList>
            {searchable && <CommandEmpty><Trans>No results.</Trans></CommandEmpty>}
            <CommandGroup>
              {items.map((item) => (
                <CommandItem
                  key={item.id}
                  value={item.id}
                  disabled={disabled || item.disabled}
                  onSelect={() => updateSelected(item)}
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4",
                      selected.find(s => s.id === item.id) ? "opacity-100" : "opacity-0"
                    )}
                  />
                  {item.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
