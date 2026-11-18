import { PropsWithChildren } from "react"

type RepeatProps = PropsWithChildren & {
  times: number
}

function Repeat({ children, times }: RepeatProps) {
  return (
    [...Array(times).keys()].map(() => children)
  )
}

export default Repeat