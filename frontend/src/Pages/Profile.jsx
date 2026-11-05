
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  UserRoundPen,
  MapPin,
  Store,
  Inbox,
  Wallet,
  LogOut,
  ChevronRight,
  UserRound,
  Camera,
} from 'lucide-react'

import Navbar from '../Components/Navbar'
import {
  getUserProfile,
  updateUserProfile,
} from '../services/api'

import { userLogout } from '../services/authentication'


function Profile() {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)

  // Profile states
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  // Logout confirmation state
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)


  // Fetch user profile
  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const data = await getUserProfile()
        setProfile(data)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchProfile()
  }, [])


  // Handle profile image upload
  const handlePhotoChange = async (event) => {
    const file = event.target.files[0]

    if (!file) return

    if (!file.type.startsWith('image/')) {
      setError('Please select a valid image.')
      return
    }

    setUploading(true)
    setError('')

    try {
      const formData = new FormData()

      formData.append('profile_image', file)

      const updatedProfile = await updateUserProfile(formData)

      setProfile(updatedProfile)
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
      event.target.value = ''
    }
  }


  // Handle logout
  const handleLogout = async () => {
    try {
      await userLogout()
    } catch (err) {
      console.error('Logout error:', err)
    } finally {
      navigate('/login', { replace: true })
    }
  }


  // Profile menu options
  const profileOptions = [
    {
      title: 'Edit Profile',
      description: 'Manage your personal details',
      icon: UserRoundPen,
    },
    {
      title: 'My Addresses',
      description: 'Manage your saved addresses',
      icon: MapPin,
    },
    {
      title: 'Host Hub',
      description: 'Manage your listed items',
      icon: Store,
    },
    {
      title: 'Incoming Requests',
      description: 'View rental requests',
      icon: Inbox,
    },
    {
      title: 'Earnings & Payouts',
      description: 'Manage your earnings',
      icon: Wallet,
    },
    {
      title: 'Logout',
      description: 'Sign out of your account',
      icon: LogOut,
    },
  ]


  // Loading screen
  if (loading) {
    return (
      <>
        <Navbar />

        <div className="flex min-h-screen items-center justify-center bg-[#FFFCF9]">
          Loading profile...
        </div>
      </>
    )
  }


  // Profile page
  return (
    <div className="min-h-screen bg-[#FFFCF9]">

      <Navbar />

      <main className="mx-auto flex max-w-5xl justify-center px-4 py-8">

        <section className="w-full max-w-md">

          <h1 className="mb-7 text-center text-2xl font-bold text-[#49362D]">
            Settings
          </h1>


          {/* Error message */}
          {error && (
            <div className="mb-5 rounded-lg bg-red-50 p-3 text-sm text-red-600">
              {error}
            </div>
          )}


          {/* User profile information */}
          {profile && (
            <div className="mb-7 flex flex-col items-center border-b border-orange-100 pb-7">

              {/* Profile image */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="group relative mb-3 h-24 w-24 overflow-hidden rounded-full border-2 border-orange-200 bg-[#FFF1E8]"
                title="Add or change profile photo"
              >
                {profile.profile_image ? (
                  <img
                    src={profile.profile_image}
                    alt="Profile"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <UserRound
                    size={42}
                    className="mx-auto text-[#D97745]"
                  />
                )}

                <span className="absolute inset-0 flex items-center justify-center bg-black/40 text-white opacity-0 transition group-hover:opacity-100">
                  <Camera size={24} />
                </span>
              </button>


              {/* Hidden image input */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handlePhotoChange}
                className="hidden"
              />


              {/* User details */}
              <h2 className="mt-2 text-lg font-semibold text-[#49362D]">
                {profile.full_name}
              </h2>

              <p className="text-sm text-gray-500">
                {profile.email}
              </p>

            </div>
          )}


          {/* Profile options */}
          <div className="overflow-hidden rounded-xl border border-orange-100 bg-white shadow-sm">

            {profileOptions.map((option, index) => {
              const Icon = option.icon

              return (
                <button
                  type="button"
                  key={option.title}
                  onClick={() => {
                    if (option.title === 'Edit Profile') {
                      navigate('/edit-profile')
                    } else if (option.title === 'My Addresses') {
                      navigate('/my-address')
                    } else if (option.title === 'Logout') {
                      setShowLogoutConfirm(true)
                    }
                  }}
                  className={`flex w-full items-center gap-3 px-4 py-4 text-left hover:bg-[#FFFAF6] ${
                    index !== profileOptions.length - 1
                      ? 'border-b border-orange-100'
                      : ''
                  }`}
                >

                  {/* Option icon */}
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#FFF1E8]">
                    <Icon
                      size={20}
                      className="text-[#D97745]"
                    />
                  </div>


                  {/* Option details */}
                  <div className="flex-1">

                    <h3 className="text-sm font-semibold text-[#49362D]">
                      {option.title}
                    </h3>

                    <p className="mt-1 text-xs text-gray-500">
                      {option.description}
                    </p>

                  </div>

                  <ChevronRight
                    size={18}
                    className="text-[#B69A89]"
                  />

                </button>
              )
            })}

          </div>


          {/* Logout confirmation modal */}
          {showLogoutConfirm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">

              <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">

                <h2 className="text-lg font-bold text-[#49362D]">
                  Confirm Logout
                </h2>

                <p className="mt-2 text-sm text-gray-600">
                  Are you sure you want to logout?
                </p>


                <div className="mt-6 flex justify-end gap-3">

                  <button
                    type="button"
                    onClick={() => setShowLogoutConfirm(false)}
                    className="rounded-lg border border-orange-200 px-4 py-2 text-sm"
                  >
                    Cancel
                  </button>

                  <button
                    type="button"
                    onClick={handleLogout}
                    className="rounded-lg bg-[#D97745] px-4 py-2 text-sm font-semibold text-white"
                  >
                    Yes, Logout
                  </button>

                </div>

              </div>

            </div>
          )}

        </section>

      </main>

    </div>
  )
}

export default Profile
