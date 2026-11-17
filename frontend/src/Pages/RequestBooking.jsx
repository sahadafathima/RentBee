import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import useCurrentUserId from '../hooks/useCurrentUserId'
import {
  getPublicItem,
  createBooking,
  getAddresses,
  checkItemAvailability,
  requestAvailabilityNotification,
  checkDiscountEligibility,
} from '../services/api'
import { calculateRentalDuration, getNextDayStr } from '../utils/dateUtils'
import {
  ChevronRight,
  ArrowLeft,
  Package,
  Calendar,
  Clock,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  CreditCard,
  MapPin,
  Edit2,
  Bell,
  Plus,
  Minus,
  Banknote,
  Sparkles,
  Tag,
} from 'lucide-react'

const isAddressComplete = (addr) => {
  if (!addr) return false
  const required = ['full_name', 'house_number', 'address', 'area', 'city', 'state', 'pincode']
  return required.every((field) => addr[field] && String(addr[field]).trim().length > 0)
}

export default function RequestBooking() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [item, setItem] = useState(null)
  const [loading, setLoading] = useState(true)

  const viewerId = useCurrentUserId()
  const isOwner = Boolean(item?.is_owner || (viewerId && item?.owner && viewerId === item.owner))

  // Booking form state - initialized from searchParams if returning from Address page
  const todayStr = new Date().toISOString().split('T')[0]
  const [startDate, setStartDate] = useState(searchParams.get('start_date') || todayStr)
  const [endDate, setEndDate] = useState(searchParams.get('end_date') || todayStr)
  const initialQuantity = parseInt(searchParams.get('quantity') || searchParams.get('requested_quantity') || '1', 10)
  const [requestedQuantity, setRequestedQuantity] = useState(initialQuantity > 0 ? initialQuantity : 1)
  const [paymentMethod, setPaymentMethod] = useState(
    searchParams.get('payment_method') === 'offline' ? 'offline' : 'online'
  )
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Address state
  const [addresses, setAddresses] = useState([])
  const [selectedAddressId, setSelectedAddressId] = useState(null)
  const [loadingAddress, setLoadingAddress] = useState(true)

  // Availability & Notification state
  const [checkingAvailability, setCheckingAvailability] = useState(false)
  const [availabilityStatus, setAvailabilityStatus] = useState(null)
  const [notifying, setNotifying] = useState(false)
  const [notifySuccess, setNotifySuccess] = useState(false)
  const [notifyMessage, setNotifyMessage] = useState('')

  // First Booking Discount Eligibility
  const [discountEligibility, setDiscountEligibility] = useState(null)

  useEffect(() => {
    let isCurrent = true
    checkDiscountEligibility()
      .then((data) => {
        if (isCurrent) setDiscountEligibility(data)
      })
      .catch(() => {
        if (isCurrent) setDiscountEligibility({ is_eligible: false })
      })
    return () => {
      isCurrent = false
    }
  }, [])

  // Load Item
  useEffect(() => {
    let isCurrent = true
    getPublicItem(id)
      .then((data) => {
        if (isCurrent) {
          setItem(data)
          setLoading(false)
        }
      })
      .catch(() => {
        if (isCurrent) setLoading(false)
      })

    return () => {
      isCurrent = false
    }
  }, [id])

  // Load Saved User Addresses & Preserve Selected Address from query parameter
  useEffect(() => {
    let isCurrent = true
    getAddresses()
      .then((data) => {
        if (!isCurrent) return
        const list = Array.isArray(data) ? data : data?.results || []
        setAddresses(list)
        const addressParam = searchParams.get('address_id')
        if (addressParam && list.some((a) => String(a.id) === String(addressParam))) {
          setSelectedAddressId(parseInt(addressParam, 10))
        } else {
          const complete = list.find(isAddressComplete) || list[0] || null
          if (complete) {
            setSelectedAddressId((prev) => (prev && list.some((a) => a.id === prev) ? prev : complete.id))
          }
        }
      })
      .catch(() => {
        if (isCurrent) setAddresses([])
      })
      .finally(() => {
        if (isCurrent) setLoadingAddress(false)
      })

    return () => {
      isCurrent = false
    }
  }, [searchParams])

  // Real-time Availability Check with quantity
  const isDateRangeInvalid = !startDate || !endDate || endDate <= startDate

  useEffect(() => {
    if (!id || !startDate || !endDate || endDate <= startDate) return

    let isCurrent = true

    checkItemAvailability(id, startDate, endDate, requestedQuantity)
      .then((data) => {
        if (!isCurrent) return
        setAvailabilityStatus(data)
        setCheckingAvailability(false)
      })
      .catch((err) => {
        if (!isCurrent) return
        setAvailabilityStatus({
          is_available: false,
          status_label: 'Unavailable',
          message: err.message || 'Could not verify availability for these dates.',
        })
        setCheckingAvailability(false)
      })

    return () => {
      isCurrent = false
    }
  }, [id, startDate, endDate, requestedQuantity])

  const effectiveAvailability = isDateRangeInvalid
    ? {
        is_available: false,
        status_label: 'Invalid Dates',
        message: 'End date must be after start date.',
      }
    : availabilityStatus

  // Calculation (difference in calendar days, return date not counted as extra rental day)
  const calculateDays = () => {
    return calculateRentalDuration(startDate, endDate)
  }

  const durationDays = calculateDays()
  const rentalPrice = item ? parseFloat(item.rental_price || 0) : 0
  const deposit = item ? parseFloat(item.deposit || 0) : 0
  const isDiscountEligible = Boolean(discountEligibility?.is_eligible)
  const originalRentalAmount = durationDays * rentalPrice * requestedQuantity
  const discountAmount = isDiscountEligible
    ? Math.round(originalRentalAmount * 0.10 * 100) / 100
    : 0
  const rentalAmount = Math.max(0, originalRentalAmount - discountAmount)
  const depositAmount = deposit * requestedQuantity
  const totalAmount = rentalAmount + depositAmount

  const selectedAddress = addresses.find((a) => a.id === selectedAddressId) || null
  const hasCompleteAddress = isAddressComplete(selectedAddress)

  // Preserve state URL for navigating to Address page and returning (including quantity, address_id, and payment_method)
  const addressQuery = selectedAddressId ? `&address_id=${selectedAddressId}` : ''
  const paymentQuery = paymentMethod ? `&payment_method=${paymentMethod}` : ''
  const editAddressUrl = `/my-address?returnTo=${encodeURIComponent(
    `/request-booking/${id}?start_date=${startDate}&end_date=${endDate}&quantity=${requestedQuantity}${addressQuery}${paymentQuery}`
  )}`

  const handleNotifyMe = async () => {
    if (!id || !startDate || !endDate) return
    setNotifying(true)
    try {
      const res = await requestAvailabilityNotification(id, startDate, endDate)
      setNotifySuccess(true)
      setNotifyMessage(res.message || 'You will be notified as soon as these dates open up!')
    } catch (err) {
      setError(err.message || 'Failed to register notification request.')
    } finally {
      setNotifying(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (isOwner) {
      setError('This is your product. You cannot request a booking for your own listing.')
      return
    }

    if (durationDays <= 0) {
      setError('Please select valid rental dates. End date must be after start date.')
      return
    }

    if (!selectedAddress || !isAddressComplete(selectedAddress)) {
      setError('Please select a complete address before booking.')
      return
    }

    if (effectiveAvailability && !effectiveAvailability.is_available) {
      setError(effectiveAvailability.message || 'This item is not available for the selected dates.')
      return
    }

    setSubmitting(true)
    try {
      const payload = {
        item_id: parseInt(id, 10),
        start_date: startDate,
        end_date: endDate,
        requested_quantity: requestedQuantity,
        address_id: selectedAddress.id,
        payment_method: paymentMethod,
      }
      const newBooking = await createBooking(payload)

      // Dedicated success page navigation
      navigate('/booking-success', { state: { booking: newBooking } })
    } catch (err) {
      setError(err.message || 'Failed to submit booking request. Please check your address and availability.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
      <div>
        <Navbar />

        <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
          {/* Breadcrumb */}
          <nav aria-label="Breadcrumb" className="mb-6">
            <ol className="flex flex-wrap items-center gap-1.5 text-xs text-gray-500 font-medium">
              <li>
                <Link to="/" className="hover:text-[#D97745] transition">
                  Home
                </Link>
              </li>
              <li>
                <ChevronRight size={13} className="text-gray-400" />
              </li>
              <li>
                <Link to="/browse" className="hover:text-[#D97745] transition">
                  Browse Items
                </Link>
              </li>
              <li>
                <ChevronRight size={13} className="text-gray-400" />
              </li>
              {item && (
                <>
                  <li>
                    <Link to={`/items/${item.id}`} className="hover:text-[#D97745] transition">
                      {item.name}
                    </Link>
                  </li>
                  <li>
                    <ChevronRight size={13} className="text-gray-400" />
                  </li>
                </>
              )}
              <li className="font-semibold text-[#352720]">Request Booking</li>
            </ol>
          </nav>

          {/* Form Container */}
          <div className="rounded-3xl border border-orange-100 bg-white p-6 sm:p-8 shadow-xs">
            {loading ? (
              <div className="space-y-4 animate-pulse">
                <div className="h-6 w-1/3 bg-orange-100/60 rounded" />
                <div className="h-4 w-2/3 bg-orange-100/40 rounded" />
                <div className="h-32 bg-orange-50 rounded-2xl" />
              </div>
            ) : item ? (
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#D97745]">
                  <Package size={15} />
                  <span>Rental Booking Request</span>
                </div>

                <h1 className="mt-1 text-2xl font-black text-[#352720] sm:text-3xl">
                  Request Booking for {item.name}
                </h1>

                {/* Item Summary Bar */}
                <div className="mt-4 rounded-2xl bg-[#FFF9F5] border border-orange-100 p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <span className="text-2xl font-black text-[#9D4C29]">
                        ₹{item.rental_price}
                      </span>
                      <span className="text-xs text-gray-500 font-medium"> / day</span>
                    </div>

                    <div className="text-right text-xs text-gray-500">
                      <span>Deposit: </span>
                      <strong className="text-[#352720]">
                        ₹{item.deposit !== undefined && item.deposit !== null ? item.deposit : 0}
                      </strong>
                    </div>
                  </div>
                </div>

                {/* Top Error Alert */}
                {error && (
                  <div className="mt-4 rounded-2xl bg-rose-50 border border-rose-200 p-4 text-xs font-semibold text-rose-800 flex items-start gap-2">
                    <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                    <span>{error}</span>
                  </div>
                )}

                {/* Owner Warning Alert */}
                {isOwner && (
                  <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-[#7A4C32] space-y-3">
                    <div className="flex items-start gap-3">
                      <AlertCircle size={20} className="text-[#D97745] shrink-0 mt-0.5" />
                      <div>
                        <h3 className="font-bold text-[#352720] text-sm">This is your product.</h3>
                        <p className="mt-1 text-xs text-gray-600 leading-relaxed">
                          You are the owner of this item. Rental booking is not permitted for your own listings.
                        </p>
                      </div>
                    </div>
                    <div className="pt-1 flex items-center gap-3">
                      <Link
                        to={`/items/${item.id}`}
                        className="rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-bold text-[#D97745] hover:bg-[#FFF9F5] transition"
                      >
                        Back to Item
                      </Link>
                      <Link
                        to="/my-listings"
                        className="rounded-xl bg-[#D97745] px-4 py-2 text-xs font-bold text-white hover:bg-[#B85D32] transition"
                      >
                        Manage in My Listings
                      </Link>
                    </div>
                  </div>
                )}

                <form onSubmit={handleSubmit} className="mt-6 space-y-6">
                  {/* STEP 1: DATE SELECTION & AVAILABILITY */}
                  <div className="rounded-2xl border border-orange-200/80 bg-[#FFFDFB] p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-bold text-[#352720] flex items-center gap-2">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#D97745] text-white text-[11px] font-bold">
                          1
                        </span>
                        <Calendar size={16} className="text-[#D97745]" />
                        Select Rental Dates & Quantity
                      </h2>

                      {checkingAvailability ? (
                        <span className="inline-flex items-center text-xs text-gray-500 animate-pulse">
                          Checking availability...
                        </span>
                      ) : effectiveAvailability?.is_available ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Available for selected dates & quantity
                        </span>
                      ) : effectiveAvailability && !effectiveAvailability.is_available ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-bold text-[#D97745] border border-amber-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-[#D97745]" />
                          Unavailable for selected dates/quantity
                        </span>
                      ) : null}
                    </div>

                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                      <div>
                        <label
                          htmlFor="start-date"
                          className="block text-xs font-semibold text-[#49362D] mb-1"
                        >
                          Start Date:
                        </label>
                        <input
                          id="start-date"
                          type="date"
                          min={todayStr}
                          value={startDate}
                          onChange={(e) => {
                            const val = e.target.value
                            setStartDate(val)
                            setCheckingAvailability(true)
                            setNotifySuccess(false)
                            setNotifyMessage('')
                            if (endDate && val >= endDate) {
                              setEndDate(getNextDayStr(val))
                            }
                          }}
                          required
                          className="w-full rounded-xl border border-orange-200 bg-white p-2.5 text-xs text-[#352720] focus:border-[#D97745] focus:outline-none focus:ring-2 focus:ring-orange-200/50"
                        />
                      </div>

                      <div>
                        <label
                          htmlFor="end-date"
                          className="block text-xs font-semibold text-[#49362D] mb-1"
                        >
                          End Date:
                        </label>
                        <input
                          id="end-date"
                          type="date"
                          min={getNextDayStr(startDate) || todayStr}
                          value={endDate}
                          onChange={(e) => {
                            setEndDate(e.target.value)
                            setCheckingAvailability(true)
                            setNotifySuccess(false)
                            setNotifyMessage('')
                          }}
                          required
                          className="w-full rounded-xl border border-orange-200 bg-white p-2.5 text-xs text-[#352720] focus:border-[#D97745] focus:outline-none focus:ring-2 focus:ring-orange-200/50"
                        />
                      </div>
                    </div>

                    {/* Quantity Selector Section */}
                    <div className="rounded-xl border border-orange-100 bg-white p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <label htmlFor="rental-quantity" className="block text-xs font-semibold text-[#49362D]">
                          Rental Quantity
                        </label>
                        <span className="text-[11px] text-gray-500">
                          {effectiveAvailability?.available_stock !== undefined
                            ? `Available stock: ${effectiveAvailability.available_stock} item${effectiveAvailability.available_stock === 1 ? '' : 's'}`
                            : item?.stock !== undefined
                            ? `Total item stock: ${item.stock} item${item.stock === 1 ? '' : 's'}`
                            : 'Select number of units to rent'}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          id="decrement-quantity"
                          aria-label="Decrease quantity"
                          onClick={() => {
                            if (requestedQuantity > 1) {
                              setRequestedQuantity((prev) => prev - 1)
                              setCheckingAvailability(true)
                              setNotifySuccess(false)
                              setNotifyMessage('')
                            }
                          }}
                          disabled={requestedQuantity <= 1}
                          className="flex h-8 w-8 items-center justify-center rounded-lg border border-orange-200 bg-[#FFFDFB] text-[#D97745] transition hover:bg-orange-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                        >
                          <Minus size={14} />
                        </button>

                        <input
                          id="rental-quantity"
                          type="number"
                          min={1}
                          max={effectiveAvailability?.available_stock || item?.stock || 99}
                          value={requestedQuantity}
                          onChange={(e) => {
                            const val = parseInt(e.target.value, 10)
                            if (!isNaN(val) && val >= 1) {
                              setRequestedQuantity(val)
                              setCheckingAvailability(true)
                              setNotifySuccess(false)
                              setNotifyMessage('')
                            }
                          }}
                          className="h-8 w-14 rounded-lg border border-orange-200 bg-white text-center text-xs font-bold text-[#352720] focus:border-[#D97745] focus:outline-none focus:ring-1 focus:ring-[#D97745]"
                        />

                        <button
                          type="button"
                          id="increment-quantity"
                          aria-label="Increase quantity"
                          onClick={() => {
                            setRequestedQuantity((prev) => prev + 1)
                            setCheckingAvailability(true)
                            setNotifySuccess(false)
                            setNotifyMessage('')
                          }}
                          disabled={
                            effectiveAvailability?.available_stock !== undefined &&
                            requestedQuantity >= effectiveAvailability.available_stock
                          }
                          className="flex h-8 w-8 items-center justify-center rounded-lg border border-orange-200 bg-[#FFFDFB] text-[#D97745] transition hover:bg-orange-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                        >
                          <Plus size={14} />
                        </button>
                      </div>
                    </div>

                    {/* Unavailability & Notify Me Banner */}
                    {effectiveAvailability && !effectiveAvailability.is_available && (
                      <div className="rounded-xl border border-amber-200 bg-[#FFF9F5] p-3.5 text-xs space-y-2.5">
                        <div className="flex items-start gap-2 text-amber-900 font-medium">
                          <AlertCircle size={15} className="text-[#D97745] shrink-0 mt-0.5" />
                          <span>
                            {effectiveAvailability.message ||
                              'This item is already booked or reserved for these dates. Please choose different dates or click Notify Me.'}
                          </span>
                        </div>

                        {notifySuccess ? (
                          <div className="flex items-center gap-2 text-emerald-700 font-semibold bg-emerald-50 p-2.5 rounded-lg border border-emerald-200">
                            <CheckCircle2 size={15} />
                            <span>{notifyMessage || 'Notification request registered! We will notify you if these dates become free.'}</span>
                          </div>
                        ) : (
                          <div className="flex items-center justify-between pt-1">
                            <span className="text-gray-500 text-[11px]">
                              Want an alert if the booking is cancelled?
                            </span>
                            <button
                              type="button"
                              onClick={handleNotifyMe}
                              disabled={notifying}
                              className="inline-flex items-center gap-1.5 rounded-lg bg-[#D97745] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#B85D32] transition disabled:opacity-50"
                            >
                              <Bell size={13} />
                              {notifying ? 'Setting alert...' : 'Notify Me'}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* STEP 2: ADDRESS SELECTION & MANAGEMENT */}
                  <div className="rounded-2xl border border-orange-200/80 bg-[#FFFDFB] p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-bold text-[#352720] flex items-center gap-2">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#D97745] text-white text-[11px] font-bold">
                          2
                        </span>
                        <MapPin size={16} className="text-[#D97745]" />
                        Select Delivery Address
                      </h2>

                      <Link
                        to={editAddressUrl}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-[#D97745] hover:underline"
                      >
                        <Plus size={13} /> Add New Address
                      </Link>
                    </div>

                    {loadingAddress ? (
                      <div className="h-20 bg-white rounded-xl border border-orange-100 animate-pulse" />
                    ) : addresses.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50/70 p-4 text-xs space-y-2">
                        <div className="flex items-start gap-2 text-amber-900 font-semibold">
                          <AlertCircle size={15} className="text-[#D97745] shrink-0 mt-0.5" />
                          <span>No saved address found. Please add an address before booking.</span>
                        </div>
                        <p className="text-gray-600 text-[11px] pl-6">
                          A complete address with house number, street, city, and PIN code is required to submit a booking request.
                        </p>
                        <div className="pt-1 pl-6">
                          <Link
                            to={editAddressUrl}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-[#D97745] px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-[#B85D32] transition"
                          >
                            <Plus size={14} /> Add Address
                          </Link>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {addresses.map((addr) => {
                          const isSelected = selectedAddressId === addr.id
                          const complete = isAddressComplete(addr)
                          return (
                            <div
                              key={addr.id}
                              onClick={() => setSelectedAddressId(addr.id)}
                              className={`rounded-xl border p-4 text-xs transition cursor-pointer ${
                                isSelected
                                  ? 'border-[#D97745] bg-[#FFFDFB] ring-2 ring-orange-200/50 shadow-xs'
                                  : 'border-orange-100 bg-white hover:border-orange-200'
                              }`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex items-start gap-3 flex-1 min-w-0">
                                  <input
                                    type="radio"
                                    name="selected_address"
                                    value={addr.id}
                                    checked={isSelected}
                                    onChange={() => setSelectedAddressId(addr.id)}
                                    className="mt-0.5 text-[#D97745] focus:ring-[#D97745]"
                                  />
                                  <div className="space-y-1 min-w-0 flex-1">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="font-bold text-[#352720] text-sm">
                                        {addr.full_name || 'Resident'}
                                      </span>
                                      <span className="rounded bg-[#FFF0E7] px-2 py-0.5 text-[10px] font-bold text-[#D97745] uppercase">
                                        {addr.address_type || 'Address'}
                                      </span>
                                      {!complete && (
                                        <span className="rounded bg-rose-50 text-rose-700 border border-rose-200 px-2 py-0.5 text-[10px] font-semibold">
                                          Incomplete
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-gray-600 leading-relaxed">
                                      {[addr.house_number, addr.address, addr.area, addr.landmark].filter(Boolean).join(', ')}
                                    </p>
                                    <p className="text-gray-800 font-medium">
                                      {[addr.city, addr.state, addr.pincode].filter(Boolean).join(', ')}
                                    </p>
                                    {!complete && (
                                      <p className="text-rose-600 font-medium text-[11px] pt-1">
                                        Please update this address before submitting your booking request.
                                      </p>
                                    )}
                                  </div>
                                </div>

                                <Link
                                  to={editAddressUrl}
                                  onClick={(e) => e.stopPropagation()}
                                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#D97745] hover:underline shrink-0"
                                >
                                  <Edit2 size={11} /> Edit
                                </Link>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>

                  {/* STEP 3: PRICE BREAKDOWN & POLICY */}
                  <div className="rounded-2xl border border-orange-200/80 bg-[#FFFDFB] p-5 space-y-3">
                    <h2 className="text-sm font-bold text-[#352720] flex items-center gap-2">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#D97745] text-white text-[11px] font-bold">
                        3
                      </span>
                      <CreditCard size={16} className="text-[#D97745]" />
                      Rental Price Summary
                    </h2>

                    <div className="rounded-xl bg-white border border-orange-100 p-4 space-y-2 text-xs">
                      {isDiscountEligible && (
                        <div className="mb-3 rounded-xl bg-gradient-to-r from-emerald-50 to-teal-50 border border-emerald-200 p-3 text-xs text-emerald-900 flex items-center justify-between gap-2 shadow-2xs">
                          <div className="flex items-center gap-2">
                            <Sparkles size={16} className="text-emerald-600 shrink-0" />
                            <div>
                              <span className="font-bold text-emerald-950 block">First Booking 10% Discount Applied!</span>
                              <span className="text-[11px] text-emerald-700">10% promotional welcome offer applied automatically.</span>
                            </div>
                          </div>
                          <span className="rounded-full bg-emerald-600 text-white font-extrabold text-[11px] px-2.5 py-0.5 shadow-2xs shrink-0">
                            10% OFF
                          </span>
                        </div>
                      )}

                      <div className="flex justify-between items-center text-gray-600">
                        <span>Rental Duration:</span>
                        <span className="font-semibold text-[#352720]">
                          {durationDays} {durationDays === 1 ? 'day' : 'days'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center text-gray-600">
                        <span>
                          {isDiscountEligible ? 'Original Rental Fee' : 'Rental Fee'} ({requestedQuantity > 1 ? `${requestedQuantity} × ` : ''}{durationDays}d × ₹{rentalPrice}):
                        </span>
                        <span className={`font-semibold ${isDiscountEligible ? 'line-through text-gray-400' : 'text-[#352720]'}`}>
                          ₹{originalRentalAmount.toFixed(2)}
                        </span>
                      </div>

                      {isDiscountEligible && (
                        <>
                          <div className="flex justify-between items-center text-emerald-700 font-medium">
                            <span className="inline-flex items-center gap-1">
                              <Tag size={13} className="text-emerald-600" /> First Booking Discount (10%):
                            </span>
                            <span className="font-bold text-emerald-700">-₹{discountAmount.toFixed(2)}</span>
                          </div>
                          <div className="flex justify-between items-center text-gray-600">
                            <span>Net Rental Fee:</span>
                            <span className="font-semibold text-[#352720]">₹{rentalAmount.toFixed(2)}</span>
                          </div>
                        </>
                      )}

                      <div className="flex justify-between items-center text-gray-600">
                        <span className="inline-flex items-center gap-1">
                          <ShieldCheck size={13} className="text-emerald-600" /> Security Deposit (Refundable)
                          {requestedQuantity > 1 ? ` (${requestedQuantity} × ₹${deposit})` : ''}:
                        </span>
                        <span className="font-semibold text-[#352720]">₹{depositAmount.toFixed(2)}</span>
                      </div>
                      <div className="pt-2 border-t border-orange-50 flex justify-between items-baseline font-bold">
                        <div>
                          <span className="text-sm text-[#352720] block">Final Payable Amount:</span>
                          {isDiscountEligible && (
                            <span className="text-[11px] font-normal text-emerald-700">
                              You save ₹{discountAmount.toFixed(2)} on this rental
                            </span>
                          )}
                        </div>
                        <span className="text-lg text-[#9D4C29]">₹{totalAmount.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>

                  {/* STEP 4: PAYMENT METHOD SELECTION */}
                  <div className="rounded-2xl border border-orange-200/80 bg-[#FFFDFB] p-5 space-y-3">
                    <h2 className="text-sm font-bold text-[#352720] flex items-center gap-2">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#D97745] text-white text-[11px] font-bold">
                        4
                      </span>
                      <CreditCard size={16} className="text-[#D97745]" />
                      Select Payment Method
                    </h2>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <label
                        htmlFor="payment-method-online"
                        className={`rounded-xl border p-4 text-xs cursor-pointer transition flex items-start gap-3 ${
                          paymentMethod === 'online'
                            ? 'border-[#D97745] bg-[#FFFDFB] ring-2 ring-orange-200/50 shadow-xs'
                            : 'border-orange-100 bg-white hover:border-orange-200'
                        }`}
                      >
                        <input
                          id="payment-method-online"
                          type="radio"
                          name="payment_method"
                          value="online"
                          checked={paymentMethod === 'online'}
                          onChange={() => setPaymentMethod('online')}
                          className="mt-0.5 text-[#D97745] focus:ring-[#D97745] cursor-pointer"
                        />
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 font-bold text-[#352720]">
                            <CreditCard size={14} className="text-[#D97745]" />
                            <span>Online Payment (Razorpay)</span>
                          </div>
                          <p className="text-[11px] text-gray-500 leading-relaxed">
                            Pay securely online via UPI, Credit/Debit Cards, or NetBanking once host approves.
                          </p>
                        </div>
                      </label>

                      <label
                        htmlFor="payment-method-offline"
                        className={`rounded-xl border p-4 text-xs cursor-pointer transition flex items-start gap-3 ${
                          paymentMethod === 'offline'
                            ? 'border-[#D97745] bg-[#FFFDFB] ring-2 ring-orange-200/50 shadow-xs'
                            : 'border-orange-100 bg-white hover:border-orange-200'
                        }`}
                      >
                        <input
                          id="payment-method-offline"
                          type="radio"
                          name="payment_method"
                          value="offline"
                          checked={paymentMethod === 'offline'}
                          onChange={() => setPaymentMethod('offline')}
                          className="mt-0.5 text-[#D97745] focus:ring-[#D97745] cursor-pointer"
                        />
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 font-bold text-[#352720]">
                            <Banknote size={14} className="text-[#D97745]" />
                            <span>Pay at Pickup (Cash)</span>
                          </div>
                          <p className="text-[11px] text-gray-500 leading-relaxed">
                            Pay cash directly to the host when picking up the item. The host confirms payment upon handover.
                          </p>
                        </div>
                      </label>
                    </div>
                  </div>

                  {/* Payment & Security Policy */}
                  <div className="rounded-2xl bg-orange-50/60 border border-orange-100 p-4 text-xs text-gray-600 flex items-start gap-2.5">
                    <ShieldCheck size={16} className="text-[#D97745] shrink-0 mt-0.5" />
                    <div>
                      <strong className="text-[#352720]">Booking & Cancellation Policy:</strong>
                      <p className="mt-0.5 leading-relaxed">
                        Submitting this request sends an inquiry to the item owner. You can cancel at any time prior to owner pickup confirmation. Exact pickup address and contact details will be revealed upon owner approval.
                      </p>
                    </div>
                  </div>

                  {/* Submit Actions */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                    <Link
                      to={`/items/${item.id}`}
                      className="inline-flex items-center gap-2 rounded-xl border border-orange-200 bg-white px-4 py-2.5 text-xs font-semibold text-[#352720] hover:bg-orange-50 transition"
                    >
                      <ArrowLeft size={14} /> Back to Item
                    </Link>

                    <button
                      type="submit"
                      disabled={
                        isOwner ||
                        submitting ||
                        durationDays <= 0 ||
                        !hasCompleteAddress ||
                        (effectiveAvailability && !effectiveAvailability.is_available)
                      }
                      className="inline-flex items-center gap-2 rounded-xl bg-[#9D4C29] px-6 py-2.5 text-xs font-semibold text-white hover:bg-[#813B20] transition disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                    >
                      {isOwner
                        ? 'Cannot Book Own Product'
                        : submitting
                        ? 'Submitting Request...'
                        : !hasCompleteAddress
                        ? 'Complete Address to Book'
                        : effectiveAvailability && !effectiveAvailability.is_available
                        ? 'Quantity/Dates Unavailable'
                        : 'Confirm & Send Booking Request'}
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-sm font-semibold text-[#352720]">Item not found</p>
                <Link
                  to="/browse"
                  className="mt-4 inline-block rounded-xl bg-[#D97745] px-4 py-2 text-xs font-semibold text-white"
                >
                  Return to Browse
                </Link>
              </div>
            )}
          </div>

          {/* Trust Assurances */}
          <div className="mt-6 grid grid-cols-2 gap-4 text-xs text-gray-500">
            <div className="flex items-center gap-2">
              <ShieldCheck size={16} className="text-[#D97745]" />
              <span>Verified Community Equipment</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock size={16} className="text-[#D97745]" />
              <span>Flexible Handover Scheduling</span>
            </div>
          </div>
        </main>
      </div>

      <Footer />
    </div>
  )
}
