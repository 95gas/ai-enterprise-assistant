import { PropsWithChildren, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import useAuth from "@/lib/hooks/useAuth";

function ProtectedRoute({ children }: PropsWithChildren) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (user === null) {
      navigate('/login', { state: { from: location.pathname }, replace: true })
    }
  }, [user, navigate, location])

  if (user) {
    return children
  } else {
    return <></>
  }
}

export default ProtectedRoute