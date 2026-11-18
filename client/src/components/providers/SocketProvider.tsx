import { createContext, PropsWithChildren, useEffect, useState } from "react";
import io, { Socket } from 'socket.io-client';

const SocketContext = createContext<Socket | undefined>(undefined)

function SocketProvider({ children }: PropsWithChildren) {
  const [socket, setSocket] = useState<Socket>()

  useEffect(() => {
    /* NOTE: could be nice to use different namespaces for chats and documents
     * but for now prepending the namespace to the message is enough
     */
    const socketInstance = io()
    setSocket(socketInstance)

    socketInstance.on('connect', () => {
      console.log(socketInstance.id)
    })

    socketInstance.on("connect_error", (error) => {
      if (socketInstance.active) {
        // temporary failure, the socket will automatically try to reconnect
        console.log(error.message)
      } else {
        // the connection was denied by the server
        // in that case, `socket.connect()` must be manually called in order to reconnect
        console.log(error.message)
      }
    })

    return () => {
      socketInstance.disconnect()
    }
  }, [])

  return (
    <SocketContext.Provider value={socket}>
      {children}
    </SocketContext.Provider>
  )
}

export default SocketProvider
export { SocketContext }