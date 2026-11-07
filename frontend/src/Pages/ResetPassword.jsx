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

  const [email, setEmail] = useState(location.state?.email || '')
  const [otp, setOtp] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [success, setSuccess] = useState(false)
  const [resending, setResending] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setMessage('')
    setErrorMessage('')

    const trimmedEmail = email.trim()
    const trimmedOtp = otp.trim()

    if (!trimmedEmail) {
      setErrorMessage('Please enter your email address.')
      return
    }

    if (!trimmedOtp) {
      setErrorMessage('Please enter the 6-digit code sent to your email.')
      return
    }

    if (newPassword.length < 8) {
      setErrorMessage('New password must be at least 8 characters long.')
      return
    }

    if (newPassword !== confirmPassword) {
      setErrorMessage('Passwords do not match.')
      return
    }

    setLoading(true)

    try {
      const verification = await verifyPasswordResetOTP({
        email: trimmedEmail,
        otp: trimmedOtp,
      })

      if (!verification.reset_token) {
        throw new Error('Reset token was not returned by the server.')
      }

      const result = await resetPasswordWithOTP({
        email: trimmedEmail,
        reset_token: verification.reset_token,
        new_password: newPassword,
      })

      setMessage(
        result.message || 'Password reset successful! You can now log in.'
      )
      setSuccess(true)
    } catch (error) {
      console.error('Password reset error:', error)
      setErrorMessage(error.message || 'Failed to reset password. Please check the code and try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleResendOTP = async () => {
    const trimmedEmail = email.trim()
    if (!trimmedEmail) {
      setErrorMessage('Please provide your email address to resend the code.')
      return
    }

    setResending(true)
    setErrorMessage('')
    setMessage('')

    try {
      const result = await sendPasswordResetOTP({ email: trimmedEmail })
      setMessage(result.message || 'A new reset code has been sent to your email.')
    } catch (error) {
      setErrorMessage(error.message || 'Could not resend reset code. Please try again.')
    } finally {
      setResending(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#FFF8F5] px-4 py-8">
      <div className="w-full max-w-md">
        <div className="mb-4">
          <Link
            to="/login"
            className="inline-flex items-center gap-2 text-sm font-medium text-[#9D4C29] transition hover:text-[#813B20]"
          >
            <span aria-hidden="true">←</span>
            Back to Login
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
              Set New Password
            </h1>
            <p className="mt-2 text-sm text-[#8B776D]">
              Enter the verification code sent to your email and choose your new password.
            </p>
          </div>

          {success ? (
            <div className="space-y-5 text-center">
              <div className="rounded-lg bg-green-50 p-4 text-sm font-medium text-green-700">
                {message}
              </div>

              <Link
                to="/login"
                className="block w-full rounded-xl bg-[#9D4C29] px-4 py-3 font-semibold text-white transition hover:bg-[#843E21]"
              >
                Log In with New Password
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <InputField
                label="Email Address"
                name="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />

              <InputField
                label="Verification Code (OTP)"
                name="otp"
                type="text"
                placeholder="Enter 6-digit code"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                required
              />

              <InputField
                label="New Password"
                name="newPassword"
                type="password"
                placeholder="At least 8 characters"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                autoComplete="new-password"
              />

              <InputField
                label="Confirm New Password"
                name="confirmPassword"
                type="password"
                placeholder="Re-enter new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                autoComplete="new-password"
              />

              {message && (
                <p role="status" className="rounded-lg bg-green-50 p-3 text-sm text-green-700">
                  {message}
                </p>
              )}

              {errorMessage && (
                <p role="alert" className="whitespace-pre-line rounded-lg bg-red-50 p-3 text-sm text-red-700">
                  {errorMessage}
                </p>
              )}

              <Button type="submit" disabled={loading}>
                {loading ? 'Resetting Password...' : 'Reset Password'}
              </Button>

              <div className="pt-2 text-center">
                <button
                  type="button"
                  onClick={handleResendOTP}
                  disabled={resending || loading}
                  className="text-sm font-semibold text-[#9D4C29] hover:underline disabled:opacity-50"
                >
                  {resending ? 'Resending Code...' : 'Resend Code'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

export default ResetPassword
