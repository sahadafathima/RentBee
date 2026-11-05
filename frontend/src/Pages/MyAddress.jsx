
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getUserProfile, createAddress ,   getAddresses } from '../services/api'

function MyAddress() {
  const [formData, setFormData] = useState({
    full_name: '',
    email: '',
    phone_number: '',
    address: '',
    house_number: '',
    area: '',
    landmark: '',
    country: 'India',
    state: '',
    city: '',
    pincode: '',
    address_type: 'Home',
  })
  const navigate = useNavigate()
  const [successMessage, setSuccessMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
 

  // Load logged-in user's profile details
useEffect(() => {
  const fetchData = async () => {
    try {
      const profile = await getUserProfile()
      const addresses = await getAddresses()

      const savedAddress = addresses[0]

      setFormData((prev) => ({
        ...prev,

        full_name: savedAddress?.full_name || profile.full_name || '',
        email: profile.email || '',
        phone_number: profile.phone_number || '',

        address: savedAddress?.address || '',
        house_number: savedAddress?.house_number || '',
        area: savedAddress?.area || '',
        landmark: savedAddress?.landmark || '',

        country: savedAddress?.country || 'India',
        state: savedAddress?.state || '',
        city: savedAddress?.city || '',
        pincode: savedAddress?.pincode || '',

        address_type: savedAddress?.address_type || 'Home',
      }))
    } catch (error) {
      console.error('Address loading failed:', error)
      setErrorMessage('Unable to load your saved address.')
    }
  }

  fetchData()
}, [])
  // Handle input changes
  const handleChange = (e) => {
    const { name, value } = e.target

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))
  }

  // Input styles
  const inputClass =
    'w-full rounded-lg border border-[#E8D9D0] bg-white px-4 py-3 text-sm text-[#49362D] outline-none focus:border-[#D97745] focus:ring-1 focus:ring-[#D97745]'

  const labelClass =
    'mb-2 block text-sm font-medium text-[#49362D]'

  // Save address to backend
  const handleSubmit = async (e) => {
    e.preventDefault()

    setSuccessMessage('')
    setErrorMessage('')
    setIsSaving(true)

    try {
      const {
        full_name,
        address,
        house_number,
        area,
        landmark,
        country,
        state,
        city,
        pincode,
        address_type,
      } = formData

      await createAddress({
        full_name,
        address,
        house_number,
        area,
        landmark,
        country,
        state,
        city,
        pincode,
        address_type,
      })

      setSuccessMessage('Your address has been successfully saved!')
    } catch (error) {
      setErrorMessage(error.message || 'Unable to save address.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#FFFCF9] px-4 py-10">
      <div className="mx-auto max-w-3xl">
        <button
  type="button"
  onClick={() => navigate(-1)}
  className="mb-6 flex items-center gap-2 text-sm font-medium text-[#927D71] hover:text-[#D97745]"
>
  ← Back to profile
</button>

        {/* Page Heading */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-[#49362D]">
            My Address
          </h1>

          <p className="mt-2 text-sm text-[#927D71]">
            Add your address details for a smooth RentBee experience.
          </p>
        </div>

        {/* Success Message */}
        {successMessage && (
          <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm font-medium text-green-700">
            {successMessage}
          </div>
        )}

        {/* Error Message */}
        {errorMessage && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
            {errorMessage}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">

          {/* Personal Details */}
          <section className="rounded-2xl border border-[#F0E5DE] bg-white p-6 shadow-sm">
            <h2 className="mb-5 text-lg font-semibold text-[#49362D]">
              Personal Details
            </h2>

            <div className="space-y-4">

              <div>
                <label className={labelClass}>Full Name</label>
                <input
                  name="full_name"
                  value={formData.full_name}
                  onChange={handleChange}
                  placeholder="Enter your full name"
                  className={inputClass}
                  required
                />
              </div>

              <div>
                <label className={labelClass}>Email Address</label>
                <input
                  value={formData.email}
                  readOnly
                  placeholder="Will be loaded from your account"
                  className={`${inputClass} bg-[#F9F5F1]`}
                />
              </div>

              <div>
                <label className={labelClass}>Phone Number</label>
                <input
                  value={formData.phone_number}
                  readOnly
                  placeholder="Will be loaded from your account"
                  className={`${inputClass} bg-[#F9F5F1]`}
                />
              </div>

            </div>
          </section>

          {/* Address Details */}
          <section className="rounded-2xl border border-[#F0E5DE] bg-white p-6 shadow-sm">
            <h2 className="mb-5 text-lg font-semibold text-[#49362D]">
              Address Details
            </h2>

            <div className="space-y-4">

              <div>
                <label className={labelClass}>Address</label>
                <input
                  name="address"
                  value={formData.address}
                  onChange={handleChange}
                  placeholder="Enter your address"
                  className={inputClass}
                  required
                />
              </div>

              <div>
                <label className={labelClass}>House Number</label>
                <input
                  name="house_number"
                  value={formData.house_number}
                  onChange={handleChange}
                  placeholder="Enter house number"
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
                  placeholder="Enter your area or locality"
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
                  placeholder="Enter a nearby landmark"
                  className={inputClass}
                />
              </div>

            </div>
          </section>

          {/* Location Details */}
          <section className="rounded-2xl border border-[#F0E5DE] bg-white p-6 shadow-sm">
            <h2 className="mb-5 text-lg font-semibold text-[#49362D]">
              Location Details
            </h2>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">

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

              <div>
                <label className={labelClass}>State</label>
                <input
                  name="state"
                  value={formData.state}
                  onChange={handleChange}
                  placeholder="Enter state"
                  className={inputClass}
                  required
                />
              </div>

              <div>
                <label className={labelClass}>City</label>
                <input
                  name="city"
                  value={formData.city}
                  onChange={handleChange}
                  placeholder="Enter city"
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
  placeholder="Enter PIN code"
  className={inputClass}
  maxLength={6}
  pattern="[0-9]{6}"
  title="Please enter a valid 6-digit PIN code"
  required
/>
              </div>

            </div>
          </section>

          {/* Address Type */}
          <section className="rounded-2xl border border-[#F0E5DE] bg-white p-6 shadow-sm">
            <h2 className="mb-5 text-lg font-semibold text-[#49362D]">
              Address Type
            </h2>

            <div className="flex flex-wrap gap-3">
              {['Home', 'Work', 'Other'].map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() =>
                    setFormData((prev) => ({
                      ...prev,
                      address_type: type,
                    }))
                  }
                  className={`rounded-lg border px-6 py-2.5 text-sm font-medium ${
                    formData.address_type === type
                      ? 'border-[#D97745] bg-[#D97745] text-white'
                      : 'border-[#E8D9D0] bg-white text-[#49362D]'
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </section>

          {/* Save Button */}
          <button
            type="submit"
            disabled={isSaving}
            className="w-full rounded-lg bg-[#D97745] px-6 py-3 font-semibold text-white transition hover:bg-[#C46638] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSaving ? 'Saving...' : 'Save Address'}
          </button>

        </form>
      </div>
    </div>
  )
}

export default MyAddress
