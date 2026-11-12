import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  getAccessToken,
  getRefreshToken,
  hasActiveSession,
  isTokenExpired,
  refreshAccessToken,
} from '../services/authentication'

function ProtectedUserRoute() {
  const location = useLocation()
  const navigate = useNavigate()
  const [isAuthenticated, setIsAuthenticated] = useState(() => hasActiveSession())
  const [isChecking, setIsChecking] = useState(() => {
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
              setIsAuthenticated(hasActiveSession())
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
      navigate('/login', { state: { from: location }, replace: true })
    }

    const handleAuthChanged = (event) => {
      if (typeof event.detail?.loggedIn === 'boolean') {
        setIsAuthenticated(event.detail.loggedIn)
      } else {
        setIsAuthenticated(hasActiveSession())
      }
    }

    window.addEventListener('rentbee:auth-expired', handleAuthExpired)
    window.addEventListener('rentbee:auth-changed', handleAuthChanged)
    return () => {
      window.removeEventListener('rentbee:auth-expired', handleAuthExpired)
      window.removeEventListener('rentbee:auth-changed', handleAuthChanged)
    }
  }, [location, navigate])

  if (!isAuthenticated && !isChecking) {
    return <Navigate to="/login" state={{ from: location }} replace />
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

export default ProtectedUserRoute
