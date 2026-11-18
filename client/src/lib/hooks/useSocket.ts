import { useContext } from "react"
import { SocketContext } from "@/components/providers/SocketProvider"

const useSocket = () => {
  const context = useContext(SocketContext)

  if (context === undefined) {
    throw Error('useSocket must be used within SocketProvider')
  }

  return context
}

export default useSocket