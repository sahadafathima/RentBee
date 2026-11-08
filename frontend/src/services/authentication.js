
const API_BASE_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) ||
  'http://127.0.0.1:8000/api'


// ==========================================
// 1. TOKEN STORAGE
// ==========================================

export function saveAuthTokens(access, refresh) {
  localStorage.setItem('rentbee_access', access)

  if (refresh) {
    localStorage.setItem('rentbee_refresh', refresh)
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
}


// ==========================================
// 2. AUTOMATIC TOKEN REFRESH
// ==========================================

// Prevent multiple refresh requests at the same time
let refreshPromise = null

export async function refreshAccessToken() {
  // If refresh is already running, reuse that request
  if (refreshPromise) {
    return refreshPromise
  }

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken()

    if (!refreshToken) {
      throw new Error('Refresh token not found.')
    }

    // Refresh API does not require an access token
    const data = await apiRequest('/token/refresh/', {
      method: 'POST',
      body: JSON.stringify({
        refresh: refreshToken,
      }),
    })

    if (!data.access) {
      throw new Error('New access token was not returned.')
    }


    saveAuthTokens(data.access, data.refresh)

    return data.access
  })()

  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}


// 3. API REQUEST FUNCTION

export async function apiRequest(endpoint, options = {}, isRetry = false) {

  console.log('Calling backend:', `${API_BASE_URL}${endpoint}`)

  
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
  ]

  const pathOnly = endpoint.split('?')[0]
  const isPublic = publicEndpoints.includes(pathOnly) || pathOnly.startsWith('/items/') || pathOnly.startsWith('/categories/')
  const requiresAuth = !isPublic

  const accessToken = requiresAuth
    ? getAccessToken()
    : null


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

  
    const isAdmin =
      localStorage.getItem('rentbee_is_admin') === 'true'

    try {

      // Get a new access token
      await refreshAccessToken()

      
      return await apiRequest(endpoint, options, true)

    } catch (error) {

      console.error('Token refresh failed:', error)

      clearAuthTokens()
      localStorage.removeItem('rentbee_is_admin')

      // Redirect to the correct login page
      window.location.replace(
        isAdmin
          ? '/admin/login?session=expired'
          : '/login?session=expired'
      )

      throw new Error(
        'Your session has expired. Please login again.',
        { cause: error }
      )
    }
  }


  // 5. HANDLE API ERRORS

  if (!response.ok) {
    let errorMessage = data.detail || data.error

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
      await apiRequest('/logout/', {
        method: 'POST',
        body: JSON.stringify({
          refresh: refreshToken,
        }),
      })
    }

  } finally {

    clearAuthTokens()
    localStorage.removeItem('rentbee_is_admin')
  }
}
