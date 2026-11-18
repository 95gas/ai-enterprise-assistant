import { LoaderCircle } from "lucide-react";
import { Button, ButtonProps } from "../button";

type LoadingButtonProps = ButtonProps & {
  loading?: boolean
}

function LoadingButton(props: LoadingButtonProps) {
  const { loading, children, ...buttonProps } = props

  return (
    <Button {...buttonProps}>
      {loading && <LoaderCircle className="w-4 h-4 mr-2 animate-spin" />}
      {children}
    </Button>
  )
}

export default LoadingButton