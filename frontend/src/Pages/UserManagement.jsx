
import { useEffect, useState } from 'react'
import AdminLayout from '../Components/AdminLayout'
import {
  getAdminUsers,
  updateAdminUserStatus,
} from '../services/api'

function UserManagement() {
  const [users, setUsers] = useState([])
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [totalUsers, setTotalUsers] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState(null)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let isCurrent = true
    const params = { page }

    if (appliedSearch) {
      params.search = appliedSearch
    }

    getAdminUsers(params)
      .then((response) => {
        if (!isCurrent) return
        setUsers(response.results || [])
        setTotalUsers(response.count || 0)
        setError('')
      })
      .catch((err) => {
        if (!isCurrent) return
        setError(err.message || 'Unable to load users.')
      })
      .finally(() => {
        if (isCurrent) setLoading(false)
      })

    return () => {
      isCurrent = false
    }
  }, [page, appliedSearch, reloadToken])

  const handleSearch = (event) => {
    event.preventDefault()
    setPage(1)
    setLoading(true)
    setAppliedSearch(search.trim())
  }

  const handleClear = () => {
    setSearch('')
    setAppliedSearch('')
    setPage(1)
    setLoading(true)
  }

  const handleUserStatus = async (user) => {
    const action = user.is_active ? 'block' : 'unblock'

    const message = user.is_active
      ? `Are you sure you want to block ${user.full_name}?`
      : `Are you sure you want to unblock ${user.full_name}?`

    if (!window.confirm(message)) return

    try {
      setActionLoading(user.id)
      await updateAdminUserStatus(user.id, action)
      setReloadToken((t) => t + 1)
    } catch (err) {
      setError(err.message || 'Unable to update user status.')
    } finally {
      setActionLoading(null)
    }
  }

  const formatDate = (date) => {
    if (!date) return '—'

    return new Date(date).toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  }

  const formatAddress = (addresses) => {
    if (!addresses || addresses.length === 0) {
      return 'Not added'
    }

    return addresses.map((address) =>
      [
        address.area,
        address.city,
        address.state,
        address.pincode,
      ].filter(Boolean).join(', ')
    ).join(' | ')
  }

  const totalPages = Math.ceil(totalUsers / 10)

  return (
    <AdminLayout
      pageTitle="User Management"
      breadcrumbs={['Admin Panel', 'Users', 'User Management']}
    >
      <div className="w-full text-[#302820]">

      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            User Management
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            View and manage registered RentBee users.
          </p>
        </div>

        <div className="rounded-lg border border-[#eee3da] bg-white px-5 py-3">
          <p className="text-sm text-gray-500">Total Users</p>
          <p className="text-2xl font-bold">{totalUsers}</p>
        </div>
      </div>

      <form
        onSubmit={handleSearch}
        className="mb-5 flex gap-3"
      >
        <input
          type="text"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search by name, email or phone number"
          className="min-w-0 flex-1 rounded-lg border border-[#e5d9cf] bg-white px-4 py-3 outline-none focus:border-[#9D4C29]"
        />

        <button
          type="submit"
          className="rounded-lg bg-[#9D4C29] px-6 py-3 font-medium text-white hover:bg-[#813d21]"
        >
          Search
        </button>

        <button
          type="button"
          onClick={handleClear}
          className="rounded-lg border border-[#e5d9cf] bg-white px-6 py-3 hover:bg-gray-50"
        >
          Clear
        </button>
      </form>

      {error && (
        <p className="mb-4 rounded-lg bg-red-100 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="overflow-x-auto rounded-xl border border-[#eee3da] bg-white">

        {loading ? (
          <p className="p-10 text-center text-gray-500">
            Loading users...
          </p>
        ) : users.length === 0 ? (
          <p className="p-10 text-center text-gray-500">
            No users found.
          </p>
        ) : (
          <table className="w-full min-w-[1500px] border-collapse text-left text-sm">

            <thead className="bg-[#f7eee7] text-[#51463d]">
              <tr>
                <th className="p-4">ID</th>
                <th className="p-4">Name</th>
                <th className="p-4">Email ID</th>
                <th className="p-4">Phone Number</th>
                <th className="p-4">Address</th>
                <th className="p-4">Email Verification</th>
                <th className="p-4">Phone Verification</th>
                <th className="p-4">Registered Date</th>
                <th className="p-4">Status</th>
                <th className="p-4">Action</th>
              </tr>
            </thead>

            <tbody>
              {users.map((user) => (
                <tr
                  key={user.id}
                  className="border-t border-[#f0e9e3] hover:bg-[#fdfaf7]"
                >
                  <td className="p-4">{user.id}</td>
                  <td className="p-4 font-medium">{user.full_name}</td>
                  <td className="p-4">{user.email}</td>
                  <td className="p-4">{user.phone_number}</td>
                  <td className="max-w-[250px] whitespace-normal p-4">
                    {formatAddress(user.addresses)}
                  </td>

                  <td className="p-4">
                    <span className={
                      user.is_email_verified
                        ? 'rounded-full bg-green-100 px-3 py-1 text-xs text-green-700'
                        : 'rounded-full bg-orange-100 px-3 py-1 text-xs text-orange-700'
                    }>
                      {user.is_email_verified ? 'Verified' : 'Not Verified'}
                    </span>
                  </td>

                  <td className="p-4">
                    <span className={
                      user.is_phone_verified
                        ? 'rounded-full bg-green-100 px-3 py-1 text-xs text-green-700'
                        : 'rounded-full bg-orange-100 px-3 py-1 text-xs text-orange-700'
                    }>
                      {user.is_phone_verified ? 'Verified' : 'Not Verified'}
                    </span>
                  </td>

                  <td className="p-4">
                    {formatDate(user.created_at)}
                  </td>

                  <td className="p-4">
                    <span className={
                      user.is_active
                        ? 'rounded-full bg-green-100 px-3 py-1 text-xs text-green-700'
                        : 'rounded-full bg-red-100 px-3 py-1 text-xs text-red-700'
                    }>
                      {user.is_active ? 'Active' : 'Blocked'}
                    </span>
                  </td>

                  <td className="p-4">
                    <button
                      type="button"
                      disabled={actionLoading === user.id}
                      onClick={() => handleUserStatus(user)}
                      className={
                        user.is_active
                          ? 'rounded-md bg-red-100 px-3 py-2 text-xs font-medium text-red-700 hover:bg-red-200 disabled:opacity-50'
                          : 'rounded-md bg-green-100 px-3 py-2 text-xs font-medium text-green-700 hover:bg-green-200 disabled:opacity-50'
                      }
                    >
                      {actionLoading === user.id
                        ? 'Please wait...'
                        : user.is_active ? 'Block' : 'Unblock'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>

          </table>
        )}
      </div>

      {!loading && totalUsers > 0 && (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-4">

          <p className="text-sm text-gray-500">
            Showing {((page - 1) * 10) + 1} - {Math.min(page * 10, totalUsers)} of {totalUsers} users
          </p>

          <div className="flex items-center gap-4">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
              className="rounded-lg border border-[#e5d9cf] bg-white px-4 py-2 disabled:opacity-40"
            >
              Previous
            </button>

            <span className="text-sm">
              Page {page} of {totalPages}
            </span>

            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
              className="rounded-lg border border-[#e5d9cf] bg-white px-4 py-2 disabled:opacity-40"
            >
              Next
            </button>
          </div>

        </div>
      )}

      </div>
    </AdminLayout>
  )
}

export default UserManagement
