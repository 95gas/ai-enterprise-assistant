import { PropsWithChildren, createContext, useEffect, useState } from "react";
import { User } from "@/lib/types/User";
import { LoaderCircle } from "lucide-react";

const AuthContext = createContext<{ auth: User | null, setAuth: (user: User | null) => void } | undefined>(undefined)

function AuthProvider({ children }: PropsWithChildren) {
  const [loading, setLoading] = useState(true)
  const [auth, setAuthState] = useState<User | null>(null)

  // TODO: move this request in the dedicate api folder
  useEffect(() => {
    fetch('/api/login', {
      method: "GET",
      credentials: 'same-origin',
      headers: {
        'Content-Type': "application/json; charset=UTF-8",
      },
    }).then(async res => {
      if (res.ok) {
        const user = await res.json()
        setAuthState(user)
      } else {
        setAuthState(null)
      }
    }).catch(() => {
      setAuthState(null)
    }).finally(() => setLoading(false))
  }, [])

  const setAuth = (user: User | null) => {
    if (user === null) {
      setAuthState(null)
    } else {
      setAuthState(user)
    }
  }

  return (
    <AuthContext.Provider value={{ auth, setAuth }}>
      {loading
        ? (
          <div className="w-full h-screen flex justify-center items-center">
            <LoaderCircle className="animate-spin"/>
          </div>
        )
        : children
      }
    </AuthContext.Provider>
  )
}

export default AuthProvider
export { AuthContext }
