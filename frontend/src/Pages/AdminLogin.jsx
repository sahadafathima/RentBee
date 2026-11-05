
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { adminLogin ,  saveAuthTokens } from '../services/authentication'

function AdminLogin() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const data = await adminLogin({ email, password })
      console.log('Admin login response:', data)

      if (!data.user?.is_staff && !data.user?.is_superuser) {
  setError('You are not authorized to access the admin panel.')
  return
}

    saveAuthTokens(data.access, data.refresh)
      localStorage.setItem('rentbee_is_admin', 'true')
      navigate('/admin/users')
    } catch (err) {
      setError(err.message || 'Admin login failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#FAF5F0] px-4 py-8">
      <div className="mx-auto max-w-md">
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-2 text-sm text-[#9D4C29] hover:text-[#813B20]"
        >
          <span aria-hidden="true">←</span> Back to Home
        </Link>

        <div className="rounded-2xl border border-[#E8DDD4] bg-white p-8 shadow-sm">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold text-[#302923]">
              RentBee Admin
            </h1>
            <p className="mt-2 text-sm text-[#766B63]">
              Sign in to manage the marketplace
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="email"
                className="mb-2 block text-sm font-medium text-[#302923]"
              >
                Admin Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter admin email"
                required
                className="w-full rounded-xl border border-[#E8DDD4] px-4 py-3 outline-none focus:border-[#9D4C29]"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-2 block text-sm font-medium text-[#302923]"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                required
                className="w-full rounded-xl border border-[#E8DDD4] px-4 py-3 outline-none focus:border-[#9D4C29]"
              />
            </div>

            {error && (
              <p className="text-sm text-red-600" role="alert">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-[#9D4C29] px-4 py-3 font-semibold text-white transition hover:bg-[#813B20] disabled:opacity-60"
            >
              {loading ? 'Signing in...' : 'Admin Login'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-[#766B63]">
            Regular user?{' '}
            <Link
              to="/login"
              className="font-semibold text-[#9D4C29] hover:underline"
            >
              User Login
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}

export default AdminLogin
