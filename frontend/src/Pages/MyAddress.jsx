import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Pencil, Trash2, ArrowLeft, MapPin, CheckCircle2 } from 'lucide-react'
import { getUserProfile, getAddresses, createAddress, updateAddress, deleteAddress } from '../services/api'
import Navbar from '../Components/Navbar'

const initialForm = {
  full_name: '',
  address: '',
  house_number: '',
  area: '',
  landmark: '',
  country: 'India',
  state: '',
  city: '',
  pincode: '',
  address_type: 'Home',
}

function MyAddress() {
  const navigate = useNavigate()
  const [addresses, setAddresses] = useState([])
  const [userProfile, setUserProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [formData, setFormData] = useState(initialForm)
  const [isSaving, setIsSaving] = useState(false)
  const [successMessage, setSuccessMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let isCurrent = true
    Promise.all([
      getUserProfile().catch(() => null),
      getAddresses().catch(() => []),
    ])
      .then(([profileData, addressesData]) => {
        if (!isCurrent) return
        setUserProfile(profileData)
        const list = Array.isArray(addressesData) ? addressesData : (addressesData?.results || [])
        setAddresses(list)
      })
      .catch((err) => {
        if (!isCurrent) return
        setErrorMessage(err.message || 'Unable to load address book.')
      })
      .finally(() => {
        if (isCurrent) setLoading(false)
      })

    return () => {
      isCurrent = false
    }
  }, [reloadToken])

  const handleStartAdd = () => {
    setFormData({
      ...initialForm,
      full_name: userProfile?.full_name || '',
    })
    setEditingId(null)
    setErrorMessage('')
    setSuccessMessage('')
    setShowForm(true)
  }

  const handleStartEdit = (addr) => {
    setFormData({
      full_name: addr.full_name || '',
      address: addr.address || '',
      house_number: addr.house_number || '',
      area: addr.area || '',
      landmark: addr.landmark || '',
      country: addr.country || 'India',
      state: addr.state || '',
      city: addr.city || '',
      pincode: addr.pincode || '',
      address_type: addr.address_type || 'Home',
    })
    setEditingId(addr.id)
    setErrorMessage('')
    setSuccessMessage('')
    setShowForm(true)
  }

  const handleDelete = async (addrId) => {
    if (!window.confirm('Are you sure you want to delete this address?')) return
    try {
      await deleteAddress(addrId)
      setSuccessMessage('Address removed successfully.')
      setReloadToken((t) => t + 1)
    } catch (err) {
      setErrorMessage(err.message || 'Failed to delete address.')
    }
  }

  const handleChange = (e) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsSaving(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      if (editingId) {
        await updateAddress(editingId, formData)
        setSuccessMessage('Address updated successfully!')
      } else {
        await createAddress(formData)
        setSuccessMessage('New address saved to your address book!')
      }
      setShowForm(false)
      setEditingId(null)
      setReloadToken((t) => t + 1)
    } catch (err) {
      setErrorMessage(err.message || 'Unable to save address.')
    } finally {
      setIsSaving(false)
    }
  }

  const inputClass =
    'w-full rounded-lg border border-[#E8D9D0] bg-white px-4 py-2.5 text-sm text-[#49362D] outline-none focus:border-[#D97745] focus:ring-1 focus:ring-[#D97745]'
  const labelClass = 'mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[#49362D]'

  return (
    <div className="min-h-screen bg-[#FFFCF9]">
      <Navbar />

      <main className="mx-auto max-w-4xl px-4 py-8">
        <button
          type="button"
          onClick={() => navigate('/profile')}
          className="mb-6 flex items-center gap-2 text-sm font-medium text-[#927D71] hover:text-[#D97745]"
        >
          <ArrowLeft size={16} /> Back to Profile
        </button>

        <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-[#49362D]">Address Book</h1>
            <p className="mt-1 text-sm text-[#927D71]">
              Manage delivery and pickup addresses for seamless RentBee rentals.
            </p>
          </div>
          {!showForm && (
            <button
              type="button"
              onClick={handleStartAdd}
              className="flex items-center gap-2 rounded-xl bg-[#D97745] px-4 py-2.5 text-sm font-semibold text-white shadow-xs hover:bg-[#B85D32] transition"
            >
              <Plus size={18} /> Add New Address
            </button>
          )}
        </div>

        {successMessage && (
          <div className="mb-6 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            <CheckCircle2 size={18} />
            <span>{successMessage}</span>
          </div>
        )}

        {errorMessage && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorMessage}
          </div>
        )}

        {showForm ? (
          <div className="rounded-2xl border border-orange-100 bg-white p-6 shadow-sm">
            <div className="mb-6 flex items-center justify-between border-b border-orange-50 pb-4">
              <h2 className="text-xl font-bold text-[#49362D]">
                {editingId ? 'Edit Address' : 'Add New Address'}
              </h2>
              <button
                type="button"
                onClick={() => {
                  setShowForm(false)
                  setEditingId(null)
                }}
                className="text-sm font-medium text-gray-400 hover:text-gray-600"
              >
                Cancel
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className={labelClass}>Full Name</label>
                  <input
                    name="full_name"
                    value={formData.full_name}
                    onChange={handleChange}
                    placeholder="Receiver's full name"
                    className={inputClass}
                    required
                  />
                </div>

                <div>
                  <label className={labelClass}>House / Flat / Building No.</label>
                  <input
                    name="house_number"
                    value={formData.house_number}
                    onChange={handleChange}
                    placeholder="e.g. 4B, Sunrise Apts"
                    className={inputClass}
                    required
                  />
                </div>

                <div>
                  <label className={labelClass}>Street Address</label>
                  <input
                    name="address"
                    value={formData.address}
                    onChange={handleChange}
                    placeholder="e.g. MG Road, Near Metro"
                    className={inputClass}
                    required
                  />
                </div>

                <div>
                  <label className={labelClass}>Area / Locality</label>
                  <input
                    name="area"
                    value={formData.area}
                    onChange={handleChange}
                    placeholder="e.g. Kaloor"
                    className={inputClass}
                    required
                  />
                </div>

                <div>
                  <label className={labelClass}>Landmark (Optional)</label>
                  <input
                    name="landmark"
                    value={formData.landmark}
                    onChange={handleChange}
                    placeholder="e.g. Opposite Post Office"
                    className={inputClass}
                  />
                </div>

                <div>
                  <label className={labelClass}>City</label>
                  <input
                    name="city"
                    value={formData.city}
                    onChange={handleChange}
                    placeholder="e.g. Kochi"
                    className={inputClass}
                    required
                  />
                </div>

                <div>
                  <label className={labelClass}>State</label>
                  <input
                    name="state"
                    value={formData.state}
                    onChange={handleChange}
                    placeholder="e.g. Kerala"
                    className={inputClass}
                    required
                  />
                </div>

                <div>
                  <label className={labelClass}>PIN Code</label>
                  <input
                    name="pincode"
                    type="text"
                    value={formData.pincode}
                    onChange={handleChange}
                    placeholder="6-digit PIN code"
                    maxLength={10}
                    className={inputClass}
                    required
                  />
                </div>

                <div>
                  <label className={labelClass}>Country</label>
                  <input
                    name="country"
                    value={formData.country}
                    onChange={handleChange}
                    className={inputClass}
                    required
                  />
                </div>
              </div>

              <div>
                <label className={labelClass}>Address Type</label>
                <div className="flex gap-3 mt-1.5">
                  {['Home', 'Work', 'Other'].map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => setFormData((prev) => ({ ...prev, address_type: type }))}
                      className={`rounded-lg border px-5 py-2 text-sm font-semibold transition ${
                        formData.address_type === type
                          ? 'border-[#D97745] bg-[#D97745] text-white shadow-xs'
                          : 'border-orange-100 bg-white text-[#49362D] hover:bg-orange-50'
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-orange-50">
                <button
                  type="button"
                  onClick={() => {
                    setShowForm(false)
                    setEditingId(null)
                  }}
                  className="rounded-lg border border-orange-200 px-5 py-2.5 text-sm font-semibold text-[#49362D] hover:bg-orange-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="rounded-lg bg-[#D97745] px-6 py-2.5 text-sm font-semibold text-white hover:bg-[#B85D32] transition disabled:opacity-60"
                >
                  {isSaving ? 'Saving...' : editingId ? 'Update Address' : 'Save Address'}
                </button>
              </div>
            </form>
          </div>
        ) : (
          <div>
            {loading ? (
              <div className="rounded-2xl border border-orange-100 bg-white p-12 text-center text-[#927D71]">
                Loading your addresses...
              </div>
            ) : addresses.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-orange-200 bg-white p-12 text-center">
                <MapPin size={40} className="mx-auto text-orange-300 mb-3" />
                <h3 className="text-lg font-bold text-[#49362D]">No saved addresses yet</h3>
                <p className="mt-1 text-sm text-[#927D71] max-w-sm mx-auto">
                  Add delivery or pickup addresses so you can rent and list equipment effortlessly.
                </p>
                <button
                  type="button"
                  onClick={handleStartAdd}
                  className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#D97745] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#B85D32] transition"
                >
                  <Plus size={16} /> Add Your First Address
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {addresses.map((addr) => (
                  <div
                    key={addr.id}
                    className="relative flex flex-col justify-between rounded-2xl border border-orange-100 bg-white p-5 shadow-xs hover:border-[#D97745]/40 transition"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span className="rounded-md bg-[#FFF0E7] px-2.5 py-0.5 text-xs font-bold text-[#D97745] uppercase tracking-wide">
                          {addr.address_type}
                        </span>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => handleStartEdit(addr)}
                            title="Edit Address"
                            className="p-1.5 text-gray-400 hover:text-[#D97745] rounded-md transition"
                          >
                            <Pencil size={16} />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDelete(addr.id)}
                            title="Delete Address"
                            className="p-1.5 text-gray-400 hover:text-red-600 rounded-md transition"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </div>

                      <h3 className="text-base font-bold text-[#49362D]">{addr.full_name}</h3>
                      <p className="mt-1.5 text-sm leading-relaxed text-[#6E584E]">
                        {[addr.house_number, addr.address, addr.area].filter(Boolean).join(', ')}
                        {addr.landmark && (
                          <span className="block text-xs text-gray-400 mt-0.5">
                            Landmark: {addr.landmark}
                          </span>
                        )}
                      </p>
                      <p className="mt-1 text-sm text-[#49362D] font-medium">
                        {[addr.city, addr.state, addr.pincode].filter(Boolean).join(', ')}
                      </p>
                      <p className="text-xs text-gray-400">{addr.country}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

export default MyAddress
