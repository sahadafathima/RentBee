
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import InputField from '../Components/InputField'
import Button from '../Components/Button'
import { sendPasswordResetOTP } from '../services/authentication'
import logo from '../assets/rentbee_logo.png'

function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const navigate = useNavigate()

  const getErrorMessage = (error) => {
    try {
      const details = JSON.parse(error.message)

      if (details.detail) return details.detail
      if (details.error) {
        return Array.isArray(details.error)
          ? details.error.join(', ')
          : details.error
      }

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

  console.log('Forgot Password form submitted')
    setErrorMessage('')

    if (newPassword !== confirmPassword) {
      setErrorMessage('Passwords do not match.')
      return
    }

    setLoading(true)

    try {
      await sendPasswordResetOTP({
        email: email.trim(),
      })

      navigate('/reset-password', {
        state: {
          email: email.trim(),
          newPassword,
        },
      })
    } catch (error) {
      console.error('Password reset OTP error:', error)
      setErrorMessage(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#FFF8F5] px-4 py-8">
      <div className="w-full max-w-md">
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
              Forgot Password?
            </h1>
            <p className="mt-2 text-sm text-[#8B776D]">
              Enter your email and choose a new password.
              We will send you an OTP to verify your email.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <InputField
              label="Email Address"
              name="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />

            <InputField
              label="New Password"
              name="new_password"
              type="password"
              placeholder="Enter new password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              autoComplete="new-password"
              required
            />

            <InputField
              label="Confirm New Password"
              name="confirm_password"
              type="password"
              placeholder="Re-enter new password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              autoComplete="new-password"
              showPasswordToggle={false}
              required
            />

            {errorMessage && (
              <p
                role="alert"
                className="whitespace-pre-line rounded-lg bg-red-50 p-3 text-sm text-red-700"
              >
                {errorMessage}
              </p>
            )}

            <Button type="submit" disabled={loading}>
              {loading ? 'Sending OTP...' : 'Reset Password'}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-[#8B776D]">
            Remember your password?{' '}
            <Link
              to="/login"
              className="font-semibold text-[#9D4C29] hover:underline"
            >
              Log In
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}

export default ForgotPassword
