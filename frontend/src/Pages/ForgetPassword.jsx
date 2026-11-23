import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import InputField from '../Components/InputField'
import Button from '../Components/Button'
import { sendPasswordResetOTP } from '../services/authentication'
import logo from '../assets/rentbee_logo.png'

function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const navigate = useNavigate()

  const handleSubmit = async (event) => {
    event.preventDefault()
    setErrorMessage('')

    const trimmedEmail = email.trim()
    if (!trimmedEmail) {
      setErrorMessage('Please enter your email address.')
      return
    }

    setLoading(true)

    try {
      await sendPasswordResetOTP({
        email: trimmedEmail,
      })

      navigate('/reset-password', {
        state: {
          email: trimmedEmail,
        },
      })
    } catch (error) {
      console.error('Password reset OTP error:', error)
      setErrorMessage(error.message || 'Unable to send password reset code.')
    } finally {
      setLoading(false)
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
              Forgot Password?
            </h1>
            <p className="mt-2 text-sm text-[#8B776D]">
              Enter your registered email address. We will send you a 6-digit verification code to reset your password.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
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

            {errorMessage && (
              <p
                role="alert"
                className="whitespace-pre-line rounded-lg bg-red-50 p-3 text-sm text-red-700"
              >
                {errorMessage}
              </p>
            )}

            <Button type="submit" disabled={loading}>
              {loading ? 'Sending Code...' : 'Send Reset Code'}
            </Button>
          </form>

          <div className="mt-6 border-t border-[#F0E4DE] pt-5 text-center">
            <p className="text-sm text-[#8B776D]">
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
    </div>
  )
}

export default ForgotPassword
