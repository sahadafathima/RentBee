
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import InputField from '../Components/InputField'
import Button from '../Components/Button'
import {
  verifyPasswordResetOTP,
  resetPasswordWithOTP,
    sendPasswordResetOTP,
} from '../services/authentication'
import logo from '../assets/rentbee_logo.png'

function ResetPassword() {
  const location = useLocation()
  const navigate = useNavigate()

  const email = location.state?.email || ''
  const newPassword = location.state?.newPassword || ''

  const [otp, setOtp] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [success, setSuccess] = useState(false)
  const [resending, setResending] = useState(false)

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
    setMessage('')
    setErrorMessage('')

    if (!email || !newPassword) {
      setErrorMessage(
        'Password reset details are missing. Please start again.'
      )
      return
    }

    if (!otp.trim()) {
      setErrorMessage('Please enter the OTP sent to your email.')
      return
    }

    setLoading(true)

    try {
      const verification = await verifyPasswordResetOTP({
        email,
        otp: otp.trim(),
      })

      if (!verification.reset_token) {
        throw new Error('Reset token was not returned by the server.')
      }

      const result = await resetPasswordWithOTP({
        email,
        reset_token: verification.reset_token,
        new_password: newPassword,
      })

      setMessage(
        result.message || 'Password reset successful. Please log in.'
      )
      setSuccess(true)
    } catch (error) {
      console.error('Password reset error:', error)
      setErrorMessage(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }
    const handleResendOTP = async () => {
    if (!email) {
      setErrorMessage('Email is missing. Please start again.')
      return
    }

    setMessage('')
    setErrorMessage('')
    setResending(true)

    try {
      const result = await sendPasswordResetOTP({ email })

      setOtp('')
      setMessage(
        result.message || 'A new OTP request has been sent.'
      )
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
    } finally {
      setResending(false)
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
              {success ? 'Password Reset Successful!' : 'Verify Your Email'}
            </h1>

            <p className="mt-2 text-sm text-[#8B776D]">
              {success
                ? 'Your password has been changed successfully.'
                : `Enter the OTP sent to ${email || 'your registered email'}.`}
            </p>
          </div>

          {!success && (
            <form onSubmit={handleSubmit} className="space-y-5">
              <InputField
                label="Email Address"
                name="email"
                type="email"
                value={email}
                onChange={() => {}}
                autoComplete="email"
                required
              />

              <InputField
                label="Email OTP"
                name="otp"
                type="text"
                placeholder="Enter your OTP"
                value={otp}
                onChange={(event) => setOtp(event.target.value)}
                autoComplete="one-time-code"
                required
              />
              <div className="text-right">
  <button
    type="button"
    onClick={handleResendOTP}
    disabled={resending || loading}
    className="text-sm font-semibold text-[#9D4C29] hover:underline disabled:opacity-50"
  >
    {resending ? 'Sending...' : 'Resend OTP'}
  </button>
</div>

              {message && (
                <p
                  role="status"
                  className="rounded-lg bg-green-50 p-3 text-sm text-green-700"
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
                {loading ? 'Verifying...' : 'Verify OTP & Reset Password'}
              </Button>
            </form>
          )}

          {success && (
            <div className="space-y-5 text-center">
              <p
                role="status"
                className="rounded-lg bg-green-50 p-3 text-sm text-green-700"
              >
                {message}
              </p>

              <Button type="button" onClick={() => navigate('/login')}>
                Back to Login
              </Button>
            </div>
          )}

          {!success && (
            <p className="mt-6 text-center text-sm text-[#8B776D]">
              <Link
                to="/forget-password"
                className="font-semibold text-[#9D4C29] hover:underline"
              >
                Start Again
              </Link>
              {' · '}
              <Link
                to="/login"
                className="font-semibold text-[#9D4C29] hover:underline"
              >
                Back to Login
              </Link>
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export default ResetPassword
