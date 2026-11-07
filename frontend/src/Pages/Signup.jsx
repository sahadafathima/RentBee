
import { useState } from 'react'
import { Link } from 'react-router-dom'
import InputField from '../Components/InputField'
import Button from '../Components/Button'
import {
  sendSignupOTP,
  verifySignupOTP,
  saveAuthTokens,
} from '../services/authentication'
import logo from '../assets/rentbee_logo.png'

function Signup() {
  const [formData, setFormData] = useState({
    full_name: '',
    email: '',
    password: '',
    phone_number: '',
  })

  const [otp, setOtp] = useState('')
  const [step, setStep] = useState('signup')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

const handleChange = (event) => {
  const { name, value } = event.target

  if (name === 'full_name') {
    if (!/^[\p{L}\s.]*$/u.test(value)) {
      return
    }
  }

  if (name === 'phone_number') {
    if (!/^\d*$/.test(value)) {
      return
    }

    if (value.length > 10) {
      return
    }
  }

  setFormData((previousData) => ({
    ...previousData,
    [name]: value,
  }))
}

  const getErrorMessage = (error) => {
    try {
      const details = JSON.parse(error.message)

      if (typeof details === 'string') return details
      if (details.detail) return details.detail
      if (details.error) return details.error

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

  
  if (step === 'signup') {
    if (!/^\d{10}$/.test(formData.phone_number)) {
      setErrorMessage('Phone number must contain exactly 10 digits.')
      return
    }
  }

  setLoading(true)

  try {
    if (step === 'signup') {
      const data = await sendSignupOTP(formData)

      setStep('verify')
      setMessage(
        data.message || 'OTP sent to your email. Please check your inbox.'
      )
    } else {
      const data = await verifySignupOTP({
        email: formData.email,
        otp: otp.trim(),
      })

      if (data.access && data.refresh) {
        saveAuthTokens(data.access, data.refresh)
      }

      setStep('success')
      setMessage(
        data.message || 'Your RentBee account has been created successfully!'
      )
    }
  } catch (error) {
    console.error('Signup error:', error)
    setErrorMessage(getErrorMessage(error))
  } finally {
    setLoading(false)
  }
}

  const handleResendOTP = async () => {
    setMessage('')
    setErrorMessage('')
    setLoading(true)

    try {
      const data = await sendSignupOTP(formData)
      setMessage(data.message || 'A new OTP has been sent to your email.')
      setOtp('')
    } catch (error) {
      setErrorMessage(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  const handleBack = () => {
    setStep('signup')
    setOtp('')
    setMessage('')
    setErrorMessage('')
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
              {step === 'success'
                ? 'Welcome to RentBee!'
                : step === 'verify'
                  ? 'Verify Your Email'
                  : 'Join RentBee'}
            </h1>

            <p className="mt-2 text-sm text-[#8B776D]">
              {step === 'success'
                ? 'Your account is ready.'
                : step === 'verify'
                  ? `Enter the OTP sent to ${formData.email}`
                  : 'Create your account'}
            </p>
          </div>

          {step !== 'success' && (
            <form onSubmit={handleSubmit} className="space-y-5">
              {step === 'signup' ? (
                <>
                  <InputField
                    label="Full Name"
                    name="full_name"
                    type="text"
                    placeholder="Enter your full name"
                    value={formData.full_name}
                    onChange={handleChange}
                    autoComplete="name"
                  />

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
                    placeholder="Create a password"
                    value={formData.password}
                    onChange={handleChange}
                    autoComplete="new-password"
                  />

                  <InputField
                    label="Phone Number"
                    name="phone_number"
                    type="tel"
                    placeholder="Enter your phone number"
                    value={formData.phone_number}
                    onChange={handleChange}
                    autoComplete="tel"
                  />
                </>
              ) : (
                <InputField
                  label="Email OTP"
                  name="otp"
                  type="text"
                  placeholder="Enter the OTP from your email"
                  value={otp}
                  onChange={(event) => setOtp(event.target.value)}
                  required
                />
              )}

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
                {loading
                  ? 'Please wait...'
                  : step === 'verify'
                    ? 'Verify OTP'
                    : 'Create Account'}
              </Button>

              {step === 'verify' && (
                <div className="space-y-3 text-center">
                  <button
                    type="button"
                    onClick={handleResendOTP}
                    disabled={loading}
                    className="text-sm font-semibold text-[#9D4C29] hover:underline disabled:opacity-50"
                  >
                    Resend OTP
                  </button>

                  <button
                    type="button"
                    onClick={handleBack}
                    disabled={loading}
                    className="block w-full text-sm text-[#8B776D] hover:text-[#9D4C29]"
                  >
                    Back to Signup
                  </button>
                </div>
              )}
            </form>
          )}

          {step === 'success' && (
            <div className="space-y-5 text-center">
              {message && (
                <p
                  role="status"
                  className="whitespace-pre-line rounded-lg bg-green-50 p-3 text-sm text-green-700"
                >
                  {message}
                </p>
              )}

              <Link
                to="/"
                className="block w-full rounded-xl bg-[#9D4C29] px-4 py-3 text-center font-semibold text-white transition hover:bg-[#843E21]"
              >
                Go to Home
              </Link>
            </div>
          )}

          {step !== 'success' && (
            <div className="mt-6 border-t border-[#F0E4DE] pt-5 text-center">
              <p className="text-sm text-[#8B776D]">
                Already have an account?{' '}
                <Link
                  to="/login"
                  className="font-semibold text-[#9D4C29] hover:underline"
                >
                  Log In
                </Link>
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Signup
