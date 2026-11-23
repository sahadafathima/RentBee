
const API_BASE_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) ||
  'http://127.0.0.1:8000/api'


// ==========================================
// 1. TOKEN STORAGE & SESSION HELPERS
// ==========================================

export function saveAuthTokens(access, refresh) {
  if (access) {
    localStorage.setItem('rentbee_access', access)
  }

  if (refresh) {
    localStorage.setItem('rentbee_refresh', refresh)
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('rentbee:auth-changed', {
        detail: { loggedIn: true, access, refresh },
      })
    )
  }
}

export function getAccessToken() {
  return localStorage.getItem('rentbee_access')
}

export function getRefreshToken() {
  return localStorage.getItem('rentbee_refresh')
}

export function clearAuthTokens() {
  localStorage.removeItem('rentbee_access')
  localStorage.removeItem('rentbee_refresh')

  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('rentbee:auth-changed', {
        detail: { loggedIn: false },
      })
    )
  }
}

/**
 * Safely parses the JSON payload from a JWT token.
 * Returns null if token is malformed.
 */
export function parseJwtPayload(token) {
  if (!token || typeof token !== 'string') return null
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    let base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    while (base64.length % 4 !== 0) {
      base64 += '='
    }
    const decoded = atob(base64)
    try {
      const jsonPayload = decodeURIComponent(
        decoded
          .split('')
          .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join('')
      )
      return JSON.parse(jsonPayload)
    } catch {
      return JSON.parse(decoded)
    }
  } catch {
    return null
  }
}

/**
 * Checks if a JWT token is expired or within a safety buffer window (default 30 seconds).
 */
export function isTokenExpired(token, bufferSeconds = 30) {
  if (!token) return true
  const payload = parseJwtPayload(token)
  if (!payload || !payload.exp) return true
  const nowInSeconds = Math.floor(Date.now() / 1000)
  return payload.exp <= nowInSeconds + bufferSeconds
}

/**
 * Returns true if the user has an active session:
 * either a non-expired access token OR a non-expired refresh token.
 */
export function hasActiveSession() {
  const access = getAccessToken()
  if (access && !isTokenExpired(access, 0)) {
    return true
  }
  const refresh = getRefreshToken()
  if (refresh && !isTokenExpired(refresh, 0)) {
    return true
  }
  return false
}

/**
 * Proactively verifies and restores the auth session on application startup.
 * If a valid refresh token exists and the access token is missing or expired,
 * it refreshes the access token in the background so all components have
 * a fresh access token ready.
 */
export async function initAuthSession() {
  if (typeof window === 'undefined') return false
  if (!hasActiveSession()) return false

  const access = getAccessToken()
  if (access && !isTokenExpired(access, 60)) {
    return true
  }

  const refresh = getRefreshToken()
  if (refresh && !isTokenExpired(refresh, 0)) {
    try {
      await refreshAccessToken()
      return true
    } catch (err) {
      if (err?.isAuthError) {
        handleSessionExpired(err)
      }
      return false
    }
  }

  return false
}

/**
 * Validates and sanitizes a post-login redirect path.
 * Must be a relative application path starting with '/' and not '//'.
 * Strictly rejects external URLs, protocol schemes, and login/signup loops.
 */
export function getSafeRedirectUrl(url) {
  if (!url || typeof url !== 'string') return '/'
  const trimmed = url.trim()
  if (!trimmed.startsWith('/') || trimmed.startsWith('//') || trimmed.includes('://')) {
    return '/'
  }
  if (trimmed.startsWith('/login') || trimmed.startsWith('/signup')) {
    return '/'
  }
  return trimmed
}

// Preserve return path and trigger auth-expired event
function handleSessionExpired(error) {
  try {
    if (typeof window !== 'undefined' && window.location) {
      const currentPath = window.location.pathname + window.location.search
      if (!currentPath.includes('/login') && !currentPath.includes('/signup')) {
        sessionStorage.setItem('rentbee_redirect_after_login', currentPath)
      }
    }
  } catch (e) {
    console.warn('Could not save return URL:', e)
  }

  clearAuthTokens()
  localStorage.removeItem('rentbee_is_admin')
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('rentbee:auth-expired', { detail: { error } })
    )
  }
}

// ==========================================
// 2. AUTOMATIC TOKEN REFRESH (Concurrency & Cross-Tab Safe)
// ==========================================

let refreshPromise = null
const REFRESH_LOCK_KEY = 'rentbee_refresh_lock'
const REFRESH_LOCK_TTL_MS = 5000

const waitMs = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export async function refreshAccessToken() {
  // If we already have a valid access token in memory/localStorage (not expiring within 30s), reuse it!
  const immediateAccess = getAccessToken()
  if (immediateAccess && !isTokenExpired(immediateAccess, 30)) {
    return immediateAccess
  }

  // If refresh is already running in this tab, reuse that request
  if (refreshPromise) {
    return refreshPromise
  }

  refreshPromise = (async () => {
    const initialRefresh = getRefreshToken()

    if (!initialRefresh) {
      const err = new Error('Refresh token not found.')
      err.isAuthError = true
      throw err
    }

    if (isTokenExpired(initialRefresh, 0)) {
      const err = new Error('Refresh token has expired.')
      err.isAuthError = true
      throw err
    }

    // Check cross-tab mutex lock
    const lockTimeStr = localStorage.getItem(REFRESH_LOCK_KEY)
    const lockTime = lockTimeStr ? parseInt(lockTimeStr, 10) : 0
    const now = Date.now()

    if (lockTime && now - lockTime < REFRESH_LOCK_TTL_MS) {
      // Another tab is refreshing. Wait briefly for it to complete.
      for (let i = 0; i < 15; i++) {
        await waitMs(200)
        const currentAccess = getAccessToken()
        const currentRefresh = getRefreshToken()
        // If the other tab saved a new access token or rotated refresh token, adopt it!
        if (currentAccess && !isTokenExpired(currentAccess, 30)) {
          return currentAccess
        }
        if (currentRefresh && currentRefresh !== initialRefresh && !isTokenExpired(currentRefresh, 0)) {
          if (currentAccess && !isTokenExpired(currentAccess, 10)) {
            return currentAccess
          }
        }
        if (!localStorage.getItem(REFRESH_LOCK_KEY)) {
          break
        }
      }
    }

    // After waiting or if no other tab was locking, check if token was refreshed
    const freshlySavedAccess = getAccessToken()
    if (freshlySavedAccess && !isTokenExpired(freshlySavedAccess, 30)) {
      return freshlySavedAccess
    }

    // Acquire lock for this tab
    localStorage.setItem(REFRESH_LOCK_KEY, Date.now().toString())

    try {
      // Re-read current refresh token from localStorage in case another tab updated it
      const tokenToSend = getRefreshToken() || initialRefresh
      if (isTokenExpired(tokenToSend, 0)) {
        const err = new Error('Refresh token has expired.')
        err.isAuthError = true
        throw err
      }

      let response
      try {
        response = await fetch(`${API_BASE_URL}/token/refresh/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            refresh: tokenToSend,
          }),
        })
      } catch (netErr) {
        console.warn('Network error while refreshing access token:', netErr)
        const err = new Error('Network error during token refresh. Keeping session.', { cause: netErr })
        err.isNetworkError = true
        throw err
      }

      if (!response.ok) {
        // Check if another tab rotated the token in the meantime
        const latestStoredRefresh = getRefreshToken()
        if (latestStoredRefresh && latestStoredRefresh !== tokenToSend && !isTokenExpired(latestStoredRefresh, 0)) {
          const currentAccess = getAccessToken()
          if (currentAccess && !isTokenExpired(currentAccess, 10)) {
            return currentAccess
          }
          // Retry once with the latest rotated refresh token
          try {
            const retryRes = await fetch(`${API_BASE_URL}/token/refresh/`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh: latestStoredRefresh }),
            })
            if (retryRes.ok) {
              const retryData = await retryRes.json()
              if (retryData.access) {
                saveAuthTokens(retryData.access, retryData.refresh || latestStoredRefresh)
                return retryData.access
              }
            }
          } catch {
            // Ignore retry net error and proceed to error handling
          }
        }

        const errText = await response.text()
        let isAuthError = false

        try {
          const parsed = JSON.parse(errText)
          if (response.status === 401 || parsed.code === 'token_not_valid') {
            isAuthError = true
          }
        } catch {
          if (response.status === 401) {
            isAuthError = true
          }
        }

        const err = new Error(`Refresh failed [${response.status}]: ${errText || response.statusText}`)
        err.status = response.status
        err.isAuthError = isAuthError
        err.isServerError = response.status >= 500
        throw err
      }

      const data = await response.json()

      if (!data.access) {
        const err = new Error('New access token was not returned.')
        err.isServerError = true
        throw err
      }

      saveAuthTokens(data.access, data.refresh || tokenToSend)
      return data.access
    } finally {
      localStorage.removeItem(REFRESH_LOCK_KEY)
    }
  })()

  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}


// 3. API REQUEST FUNCTION

export async function apiRequest(endpoint, options = {}, isRetry = false) {
  const publicEndpoints = [
    '/signup/',
    '/signup/send-otp/',
    '/signup/verify-otp/',

    '/login/',

    '/admin/login/',

    '/password-reset/send-otp/',
    '/password-reset/verify-otp/',
    '/password-reset/reset/',

    '/token/refresh/',
    '/logout/',
    '/bookings/check-availability/',
  ]

  const pathOnly = endpoint.split('?')[0]
  const isGet = !options.method || options.method.toUpperCase() === 'GET'
  const isItemDetail = /^\/items\/\d+\/?$/.test(pathOnly)
  const isPublic =
    publicEndpoints.includes(pathOnly) ||
    (isGet && pathOnly.startsWith('/items/') && !pathOnly.startsWith('/items/mine/')) ||
    (isGet && pathOnly.startsWith('/categories/')) ||
    pathOnly.startsWith('/bookings/check-availability')
  const requiresAuth = !isPublic

  let accessToken = null

  if (requiresAuth) {
    accessToken = getAccessToken()
    // Pre-emptive Token Refresh:
    // If request requires auth and access token is missing or expiring within 30 seconds
    if (!isRetry) {
      const refreshToken = getRefreshToken()
      if (refreshToken && (!accessToken || isTokenExpired(accessToken, 30))) {
        try {
          accessToken = await refreshAccessToken()
        } catch (refreshErr) {
          if (refreshErr.isAuthError) {
            handleSessionExpired(refreshErr)
            throw new Error('Your session has expired. Please login again.', { cause: refreshErr })
          }
          // On network or server error, preserve session and proceed
        }
      }
    }
  } else if (isItemDetail && hasActiveSession()) {
    // Targeted optional auth for item details: attach token if logged in, but preserve guest access
    accessToken = getAccessToken()
    if (!isRetry) {
      const refreshToken = getRefreshToken()
      if (refreshToken && (!accessToken || isTokenExpired(accessToken, 30))) {
        try {
          accessToken = await refreshAccessToken()
        } catch {
          // If refresh fails for a public item detail, proceed as guest without Authorization header
          accessToken = null
        }
      }
    }
  }

  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData

  const headers = {
    ...(isFormData
      ? {}
      : { 'Content-Type': 'application/json' }),

    ...options.headers,

    ...(accessToken
      ? { Authorization: `Bearer ${accessToken}` }
      : {}),
  }

  if (isFormData && headers['Content-Type']) {
    delete headers['Content-Type']
  }

  let response

  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    })

  } catch (error) {
    console.error('Network/CORS error:', error)

    throw new Error(
      'Cannot connect to the backend. Check Django server and CORS settings.',
      { cause: error }
    )
  }

 
  const text = await response.text()

  let data

  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    data = {
      error: text || 'Invalid response from server.',
    }
  }


  if (
    response.status === 401 &&
    requiresAuth &&
    !isRetry
  ) {
    try {
      // Check if another parallel request already refreshed the access token
      const currentToken = getAccessToken()
      if (currentToken && currentToken !== accessToken && !isTokenExpired(currentToken, 10)) {
        return await apiRequest(endpoint, options, true)
      }

      // Get a new access token
      await refreshAccessToken()
      return await apiRequest(endpoint, options, true)
    } catch (error) {
      if (error.isAuthError) {
        console.error('Session genuinely expired:', error)
        handleSessionExpired(error)
        throw new Error(
          'Your session has expired. Please login again.',
          { cause: error }
        )
      }

      // For temporary network or server errors, do not log out
      console.warn('Temporary error during token refresh (session preserved):', error)
      throw error
    }
  }


  // 5. HANDLE API ERRORS

  if (!response.ok) {
    let errorMessage = data.detail || data.error || data.message

    if (!errorMessage && typeof data === 'object' && data !== null) {
      const fieldErrors = Object.entries(data)
        .map(([field, errs]) => `${field}: ${Array.isArray(errs) ? errs.join(', ') : errs}`)
        .filter(Boolean)
      if (fieldErrors.length > 0) {
        errorMessage = fieldErrors.join(' | ')
      }
    }

    if (!errorMessage) {
      errorMessage = `Request failed with status ${response.status}`
    } else if (Array.isArray(errorMessage)) {
      errorMessage = errorMessage.join(', ')
    }

    throw new Error(errorMessage)
  }

  return data
}

// 6. SIGNUP OTP

export function sendSignupOTP(data) {
  return apiRequest('/signup/send-otp/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function verifySignupOTP(data) {
  return apiRequest('/signup/verify-otp/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// 7. PASSWORD RESET OTP

export function sendPasswordResetOTP(data) {
  return apiRequest('/password-reset/send-otp/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function verifyPasswordResetOTP(data) {
  return apiRequest('/password-reset/verify-otp/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function resetPasswordWithOTP(data) {
  return apiRequest('/password-reset/reset/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// 8. USER LOGIN

export function userLogin(data) {
  return apiRequest('/login/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// 9. ADMIN LOGIN

export function adminLogin(data) {
  return apiRequest('/admin/login/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}


// 10. USER LOGOUT

export async function userLogout() {
  const refreshToken = getRefreshToken()

  try {
    if (refreshToken) {
      // Direct POST to /logout/ using fetch to safely invalidate refresh token
      await fetch(`${API_BASE_URL}/logout/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
        },
        body: JSON.stringify({
          refresh: refreshToken,
        }),
      }).catch((err) => {
        console.warn('Backend logout notification failed:', err)
      })
    }
  } finally {
    clearAuthTokens()
    localStorage.removeItem('rentbee_is_admin')
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('rentbee:auth-expired'))
    }
  }
}
