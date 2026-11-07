import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { getAccessToken } from '../services/authentication'

function ProtectedUserRoute() {
  const location = useLocation()
  const token = getAccessToken()

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}

export default ProtectedUserRoute

