
import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import {
  getAccessToken,
  getRefreshToken,
  hasActiveSession,
  isTokenExpired,
  refreshAccessToken,
} from '../services/authentication'

function ProtectedAdminRoute() {
  const isAdmin = typeof window !== 'undefined' && localStorage.getItem('rentbee_is_admin') === 'true'
  const [isAuthenticated, setIsAuthenticated] = useState(() => hasActiveSession() && isAdmin)
  const [isChecking, setIsChecking] = useState(() => {
    if (!isAdmin) return false
    const access = getAccessToken()
    const refresh = getRefreshToken()
    return Boolean(refresh && (!access || isTokenExpired(access, 0)))
  })

  useEffect(() => {
    let active = true

    if (isChecking) {
      refreshAccessToken()
        .then(() => {
          if (active) {
            setIsAuthenticated(true)
            setIsChecking(false)
          }
        })
        .catch((err) => {
          if (active) {
            if (err?.isAuthError) {
              setIsAuthenticated(false)
            } else {
              const currentAdmin = localStorage.getItem('rentbee_is_admin') === 'true'
              setIsAuthenticated(hasActiveSession() && currentAdmin)
            }
            setIsChecking(false)
          }
        })
    }

    return () => {
      active = false
    }
  }, [isChecking])

  useEffect(() => {
    const handleAuthExpired = () => {
      setIsAuthenticated(false)
      setIsChecking(false)
    }

    const handleAuthChanged = (event) => {
      const adminFlag = localStorage.getItem('rentbee_is_admin') === 'true'
      if (typeof event.detail?.loggedIn === 'boolean') {
        setIsAuthenticated(event.detail.loggedIn && adminFlag)
      } else {
        setIsAuthenticated(hasActiveSession() && adminFlag)
      }
    }

    window.addEventListener('rentbee:auth-expired', handleAuthExpired)
    window.addEventListener('rentbee:auth-changed', handleAuthChanged)
    return () => {
      window.removeEventListener('rentbee:auth-expired', handleAuthExpired)
      window.removeEventListener('rentbee:auth-changed', handleAuthChanged)
    }
  }, [])

  if (!isAuthenticated && !isChecking) {
    return <Navigate to="/admin/login" replace />
  }

  if (isChecking) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-[#D97745] border-t-transparent" />
      </div>
    )
  }

  return <Outlet />
}

export default ProtectedAdminRoute
