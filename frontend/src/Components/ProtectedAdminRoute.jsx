
import { Navigate, Outlet } from 'react-router-dom'

function ProtectedAdminRoute() {
  const token = localStorage.getItem('rentbee_access')
  const isAdmin = localStorage.getItem('rentbee_is_admin')

  if (!token || isAdmin !== 'true') {
    return <Navigate to="/admin/login" replace />
  }

  return <Outlet />
}

export default ProtectedAdminRoute
