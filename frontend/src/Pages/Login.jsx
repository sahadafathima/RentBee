
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import InputField from '../Components/InputField'
import Button from '../Components/Button'
import { userLogin, saveAuthTokens } from '../services/authentication'
import logo from '../assets/rentbee_logo.png'

function Login() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isSessionExpired = searchParams.get('session') === 'expired'

  const [formData, setFormData] = useState({
    email: '',
    password: '',
  })

  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  const handleChange = (event) => {
    const { name, value } = event.target

    setFormData((previousData) => ({
      ...previousData,
      [name]: value,
    }))
  }

  const getErrorMessage = (error) => {
    try {
      const details = JSON.parse(error.message)

      if (details.error) {
        return Array.isArray(details.error)
          ? details.error.join(', ')
          : details.error
      }

      if (details.detail) return details.detail

      return Object.entries(details)
        .map(([field, errors]) => {
          const text = Array.isArray(errors)
            ? errors.join(', ')
            : String(errors)

          return `${field}: ${text}`
        })
        .join('\n')
    } catch {
      return error.message || 'Something went wrong. Please try again.'
    }
  }

 const handleSubmit = async (event) => {
  event.preventDefault()
  setMessage('')
  setErrorMessage('')
  setLoading(true)

  try {
    const data = await userLogin({
      email: formData.email.trim(),
      password: formData.password,
    })

    if (!data.access || !data.refresh) {
      throw new Error(
        'Access or refresh token was not returned by the server.'
      )
    }

    saveAuthTokens(data.access, data.refresh)

    setMessage('Login successful! Welcome to RentBee.')

    setTimeout(() => {
      const redirectUrl = sessionStorage.getItem('rentbee_redirect_after_login')
      if (redirectUrl) {
        sessionStorage.removeItem('rentbee_redirect_after_login')
        navigate(redirectUrl)
      } else {
        navigate('/')
      }
    }, 1500)

  } catch (error) {
    console.error('Login error:', error)
    setErrorMessage(getErrorMessage(error))
  } finally {
    setLoading(false)
  }
}

const handleForgotPassword = () => {
  navigate('/forget-password')
}
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#FFF8F5] px-4 py-8">
      <div className="w-full max-w-md">
        
<div className="mb-4">
  <Link
    to="/"
    className="inline-flex items-center gap-2 text-sm font-medium text-[#9D4C29] transition hover:text-[#813B20]"
  >
    <span aria-hidden="true">←</span>
    Back to Home
  </Link>
</div>

        <div className="mb-6 flex justify-center">
          <img
            src={logo}
            alt="RentBee Logo"
            className="h-16 w-auto object-contain"
          />
        </div>

        <div className="rounded-2xl border border-[#F0E4DE] bg-white p-6 shadow-lg sm:p-8">
          <div className="mb-7 text-center">
            <h1 className="text-3xl font-bold text-[#493329]">
              Welcome Back
            </h1>

            <p className="mt-2 text-sm text-[#8B776D]">
              Log in to your RentBee account
            </p>
          </div>

          {isSessionExpired && !errorMessage && (
            <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              Your session has expired. Please sign in to resume where you left off.
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <InputField
              label="Email Address"
              name="email"
              type="email"
              placeholder="you@example.com"
              value={formData.email}
              onChange={handleChange}
              autoComplete="email"
            />

            <InputField
              label="Password"
              name="password"
              type="password"
              placeholder="Enter your password"
              value={formData.password}
              onChange={handleChange}
              autoComplete="current-password"
            />

            <div className="-mt-2 text-right">
              <button
                type="button"
                onClick={handleForgotPassword}
                className="text-sm font-semibold text-[#9D4C29] hover:underline"
              >
                Forgot Password?
              </button>
            </div>

            {message && (
              <p
                role="status"
                className="whitespace-pre-line rounded-lg bg-green-50 p-3 text-sm text-green-700"
              >
                {message}
              </p>
            )}

            {errorMessage && (
              <p
                role="alert"
                className="whitespace-pre-line rounded-lg bg-red-50 p-3 text-sm text-red-700"
              >
                {errorMessage}
              </p>
            )}

            <Button type="submit" disabled={loading}>
              {loading ? 'Please wait...' : 'Log In'}
            </Button>
          </form>

          <div className="mt-6 border-t border-[#F0E4DE] pt-5 text-center">
            <p className="text-sm text-[#8B776D]">
              Don't have an account?{' '}
              <Link
                to="/signup"
                className="font-semibold text-[#9D4C29] hover:underline"
              >
                Sign Up
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Login
