
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  UserRound,
  Mail,
  Phone,
  Lock,
  Eye,
  EyeOff,
} from 'lucide-react'

import Navbar from '../Components/Navbar'

import {
  getUserProfile,
  updateUserProfile,
  sendEmailChangeOTP,
  verifyEmailChangeOTP,
  changePassword,
} from '../services/api'

function EditProfile() {
  const navigate = useNavigate()

  // Profile details
  const [profile, setProfile] = useState({
    full_name: '',
    email: '',
    phone_number: '',
  })

  // Email change states
  const [newEmail, setNewEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [otpSent, setOtpSent] = useState(false)
  const [sendingOTP, setSendingOTP] = useState(false)
  const [verifyingOTP, setVerifyingOTP] = useState(false)

  // Password change states
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })

  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false,
  })

  const [changingPassword, setChangingPassword] = useState(false)
  const [showPasswordFields, setShowPasswordFields] = useState(false)

  // General states
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Fetch profile details
  useEffect(() => {
    async function fetchProfile() {
      try {
        const data = await getUserProfile()

        setProfile(data)
        setNewEmail(data.email || '')
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchProfile()
  }, [])

  // Handle profile input changes
  const handleChange = (e) => {
    setProfile((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }))
  }

  // Save profile changes
  const handleSave = async (e) => {
    e.preventDefault()

    setSaving(true)
    setError('')
    setSuccess('')

    try {
      const formData = new FormData()
      formData.append('full_name', profile.full_name)

      const updated = await updateUserProfile(formData)

      setProfile((prev) => ({
        ...prev,
        ...updated,
      }))

      setSuccess('Profile updated successfully.')

      setTimeout(() => {
        navigate('/profile')
      }, 2000)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // Send email change OTP
  const handleSendOTP = async () => {
    setError('')
    setSuccess('')

    if (!newEmail.trim()) {
      setError('Please enter your new email address.')
      return
    }

    if (
      newEmail.trim().toLowerCase() ===
      profile.email.toLowerCase()
    ) {
      setError('This is already your current email.')
      return
    }

    setSendingOTP(true)

    try {
      const response = await sendEmailChangeOTP(newEmail.trim())

      setOtpSent(true)
      setOtp('')
      setSuccess(response.message || 'OTP sent successfully.')
    } catch (err) {
      setError(err.message)
    } finally {
      setSendingOTP(false)
    }
  }

  // Verify email change OTP
  const handleVerifyOTP = async () => {
    setError('')
    setSuccess('')

    if (!otp.trim()) {
      setError('Please enter the OTP.')
      return
    }

    setVerifyingOTP(true)

    try {
      await verifyEmailChangeOTP(otp.trim())

      setProfile((prev) => ({
        ...prev,
        email: newEmail.trim().toLowerCase(),
      }))

      setOtpSent(false)
      setOtp('')

      setSuccess('Email address updated and verified successfully.')
    } catch (err) {
      setError(err.message)
    } finally {
      setVerifyingOTP(false)
    }
  }

  // Handle password input changes
  const handlePasswordChange = (e) => {
    setPasswordData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }))
  }

  // Toggle password visibility
  const togglePasswordVisibility = (field) => {
    setShowPasswords((prev) => ({
      ...prev,
      [field]: !prev[field],
    }))
  }

  // Change password
  const handleChangePassword = async () => {
    setError('')
    setSuccess('')

    const {
      current_password,
      new_password,
      confirm_password,
    } = passwordData

    if (!current_password || !new_password || !confirm_password) {
      setError('Please fill in all password fields.')
      return
    }

    if (new_password !== confirm_password) {
      setError('New passwords do not match.')
      return
    }

    if (current_password === new_password) {
      setError('New password must be different from current password.')
      return
    }

    setChangingPassword(true)

    try {
      const response = await changePassword(passwordData)

      setSuccess(
        response.message || 'Password changed successfully.'
      )

      setPasswordData({
        current_password: '',
        new_password: '',
        confirm_password: '',
      })

      setShowPasswords({
        current: false,
        new: false,
        confirm: false,
      })

      setShowPasswordFields(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setChangingPassword(false)
    }
  }

  // Cancel password change
  const handleCancelPassword = () => {
    setShowPasswordFields(false)

    setPasswordData({
      current_password: '',
      new_password: '',
      confirm_password: '',
    })

    setShowPasswords({
      current: false,
      new: false,
      confirm: false,
    })
  }

  // Loading screen
  if (loading) {
    return (
      <div className="p-8 text-center">
        Loading profile...
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#FFFCF9]">
      <Navbar />

      <main className="mx-auto max-w-2xl px-4 py-10">

        {/* Back to Profile */}
        <button
          type="button"
          onClick={() => navigate('/profile')}
          className="mb-6 flex items-center gap-2 text-sm text-[#8A6552]"
        >
          <ArrowLeft size={18} />
          Back to Profile
        </button>

        <div className="rounded-2xl border border-orange-100 bg-white p-6 shadow-sm">

          {/* Page Heading */}
          <h1 className="text-2xl font-bold text-[#49362D]">
            Edit Profile
          </h1>

          <p className="mt-2 text-sm text-gray-500">
            Manage your personal information.
          </p>

          {/* Error Message */}
          {error && (
            <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">
              {error}
            </p>
          )}

          {/* Success Message */}
          {success && (
            <p className="mt-4 rounded-lg bg-green-50 p-3 text-sm text-green-700">
              {success}
            </p>
          )}

          <form onSubmit={handleSave} className="mt-6 space-y-5">

            {/* Full Name */}
            <div>
              <label className="mb-2 block text-sm font-medium text-[#49362D]">
                Full Name
              </label>

              <div className="flex items-center gap-3 rounded-lg border border-orange-100 px-3">
                <UserRound size={18} className="text-[#D97745]" />

                <input
                  type="text"
                  name="full_name"
                  value={profile.full_name}
                  onChange={handleChange}
                  required
                  className="w-full py-3 text-sm outline-none"
                />
              </div>
            </div>

            {/* Email Change */}
            <div>
              <label className="mb-2 block text-sm font-medium text-[#49362D]">
                Email Address
              </label>

              <div className="flex items-center gap-3 rounded-lg border border-orange-100 px-3">
                <Mail size={18} className="text-[#D97745]" />

                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => {
                    setNewEmail(e.target.value)
                    setOtpSent(false)
                    setOtp('')
                  }}
                  required
                  className="w-full py-3 text-sm outline-none"
                />
              </div>

              {!otpSent ? (
                <button
                  type="button"
                  onClick={handleSendOTP}
                  disabled={sendingOTP}
                  className="mt-3 rounded-lg bg-[#FFF1E8] px-4 py-2 text-sm font-semibold text-[#D97745] disabled:opacity-60"
                >
                  {sendingOTP ? 'Sending OTP...' : 'Send OTP'}
                </button>
              ) : (
                <div className="mt-4 space-y-3">

                  <p className="text-xs text-gray-500">
                    Enter the 6-digit OTP sent to your new email address.
                  </p>

                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="Enter 6-digit OTP"
                    value={otp}
                    onChange={(e) =>
                      setOtp(e.target.value.replace(/\D/g, ''))
                    }
                    className="w-full rounded-lg border border-orange-100 px-3 py-3 text-sm outline-none focus:border-[#D97745]"
                  />

                  <button
                    type="button"
                    onClick={handleVerifyOTP}
                    disabled={verifyingOTP}
                    className="rounded-lg bg-[#D97745] px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
                  >
                    {verifyingOTP ? 'Verifying...' : 'Verify OTP'}
                  </button>

                </div>
              )}
            </div>

            {/* Phone Number */}
            <div>
              <label className="mb-2 block text-sm font-medium text-[#49362D]">
                Phone Number
              </label>

              <div className="flex items-center gap-3 rounded-lg border border-orange-100 px-3">
                <Phone size={18} className="text-[#D97745]" />

                <input
                  type="tel"
                  value={profile.phone_number}
                  readOnly
                  className="w-full bg-transparent py-3 text-sm outline-none"
                />
              </div>

              <p className="mt-2 text-xs text-gray-500">
                Phone number change is currently unavailable.
              </p>
            </div>

            {/* Change Password */}
            <div className="rounded-xl border border-orange-100 p-4">

              <div className="flex items-center gap-2">
                <Lock size={18} className="text-[#D97745]" />

                <h2 className="font-semibold text-[#49362D]">
                  Change Password
                </h2>
              </div>

              {!showPasswordFields ? (
                <button
                  type="button"
                  onClick={() => setShowPasswordFields(true)}
                  className="mt-4 w-full rounded-lg bg-[#FFF1E8] py-3 font-semibold text-[#D97745] hover:bg-orange-100"
                >
                  Change Password
                </button>
              ) : (
                <div className="mt-4 space-y-4">

                  {/* Current Password */}
                  <div>
                    <label className="mb-2 block text-sm font-medium text-[#49362D]">
                      Current Password
                    </label>

                    <div className="flex items-center rounded-lg border border-orange-100 px-3 focus-within:border-[#D97745]">
                      <input
                        type={showPasswords.current ? 'text' : 'password'}
                        name="current_password"
                        value={passwordData.current_password}
                        onChange={handlePasswordChange}
                        placeholder="Enter current password"
                        autoComplete="current-password"
                        className="w-full py-3 text-sm outline-none"
                      />

                      <button
                        type="button"
                        onClick={() => togglePasswordVisibility('current')}
                        className="text-gray-500"
                        aria-label={showPasswords.current ? 'Hide current password' : 'Show current password'}
                      >
                        {showPasswords.current ? (
                          <EyeOff size={18} />
                        ) : (
                          <Eye size={18} />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* New Password */}
                  <div>
                    <label className="mb-2 block text-sm font-medium text-[#49362D]">
                      New Password
                    </label>

                    <div className="flex items-center rounded-lg border border-orange-100 px-3 focus-within:border-[#D97745]">
                      <input
                        type={showPasswords.new ? 'text' : 'password'}
                        name="new_password"
                        value={passwordData.new_password}
                        onChange={handlePasswordChange}
                        placeholder="Enter new password"
                        autoComplete="new-password"
                        className="w-full py-3 text-sm outline-none"
                      />

                      <button
                        type="button"
                        onClick={() => togglePasswordVisibility('new')}
                        className="text-gray-500"
                        aria-label={showPasswords.new ? 'Hide new password' : 'Show new password'}
                      >
                        {showPasswords.new ? (
                          <EyeOff size={18} />
                        ) : (
                          <Eye size={18} />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Confirm New Password */}
                  <div>
                    <label className="mb-2 block text-sm font-medium text-[#49362D]">
                      Confirm New Password
                    </label>

                    <input
                      type="password"
                      name="confirm_password"
                      value={passwordData.confirm_password}
                      onChange={handlePasswordChange}
                      placeholder="Confirm new password"
                      autoComplete="new-password"
                      className="w-full rounded-lg border border-orange-100 px-3 py-3 text-sm outline-none focus:border-[#D97745]"
                    />
                  </div>

                  {/* Update Password */}
                  <button
                    type="button"
                    onClick={handleChangePassword}
                    disabled={changingPassword}
                    className="w-full rounded-lg bg-[#D97745] py-3 font-semibold text-white hover:bg-[#C56838] disabled:opacity-60"
                  >
                    {changingPassword ? 'Updating...' : 'Update Password'}
                  </button>

                  {/* Cancel */}
                  <button
                    type="button"
                    onClick={handleCancelPassword}
                    className="w-full text-sm text-gray-500"
                  >
                    Cancel
                  </button>

                </div>
              )}
            </div>

            {/* Save Profile Changes */}
            <button
              type="submit"
              disabled={saving}
              className="w-full rounded-lg bg-[#D97745] py-3 font-semibold text-white hover:bg-[#C56838] disabled:opacity-60"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>

          </form>
        </div>
      </main>
    </div>
  )
}

export default EditProfile
