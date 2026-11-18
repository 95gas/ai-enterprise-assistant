import { useContext } from "react";
import { AuthContext } from "@/components/providers/AuthProvider";
import { User } from "../types/User";

const useAuth = () => {
  const context = useContext(AuthContext)

  if (context === undefined) {
    throw Error('useAuth must be used within AuthProvider')
  }

  // TODO: move theese requests in the dedicated api folder
  return {
    user: context.auth,
    login: async (email: string, password: string) => {
      const res = await fetch('/api/login', {
        method: "POST",
        credentials: 'same-origin',
        body: JSON.stringify({email, password}),
        headers: {
          'Content-Type': "application/json; charset=UTF-8",
        },
      })

      if (res.ok) {
        const user = await res.json()
        context.setAuth(user)
      }

      return res
    },
    logout: async () => {
      const res = await fetch('/api/logout', {
        method: "POST",
        credentials: 'same-origin',
      })

      if (res.ok) {
        context.setAuth(null)
      }

      return res
    },
    update: async (userInfo: Omit<User, "id">) => {
      // TODO: actually update the user profile
      console.log(userInfo)
      const res = await fetch('/api/healthcheck', {
        method: "GET",
        credentials: 'same-origin',
        // body: JSON.stringify(userInfo)
      })

      if (res.ok) {
        // TODO: logout user if passowrd hase been changed or/and update user data
        //context.setAuth(null)
      }

      return res
    }
  }
}

export default useAuth