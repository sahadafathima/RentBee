import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import {
  getPublicItem,
  createBooking,
  getAddresses,
  checkItemAvailability,
  requestAvailabilityNotification,
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

  // Booking form state - initialized from searchParams if returning from Address page
  const todayStr = new Date().toISOString().split('T')[0]
  const [startDate, setStartDate] = useState(searchParams.get('start_date') || todayStr)
  const [endDate, setEndDate] = useState(searchParams.get('end_date') || todayStr)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // Address state
  const [userAddress, setUserAddress] = useState(null)
  const [loadingAddress, setLoadingAddress] = useState(true)

  // Availability & Notification state
  const [checkingAvailability, setCheckingAvailability] = useState(false)
  const [availabilityStatus, setAvailabilityStatus] = useState(null)
  const [notifying, setNotifying] = useState(false)
  const [notifySuccess, setNotifySuccess] = useState(false)
  const [notifyMessage, setNotifyMessage] = useState('')

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

  // Load Saved User Address
  useEffect(() => {
    let isCurrent = true
    getAddresses()
      .then((data) => {
        if (!isCurrent) return
        const list = Array.isArray(data) ? data : data?.results || []
        const complete = list.find(isAddressComplete) || list[0] || null
        setUserAddress(complete)
      })
      .catch(() => {
        if (isCurrent) setUserAddress(null)
      })
      .finally(() => {
        if (isCurrent) setLoadingAddress(false)
      })

    return () => {
      isCurrent = false
    }
  }, [])

  // Real-time Availability Check
  const isDateRangeInvalid = !startDate || !endDate || endDate <= startDate

  useEffect(() => {
    if (!id || !startDate || !endDate || endDate <= startDate) return

    let isCurrent = true

    checkItemAvailability(id, startDate, endDate)
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
  }, [id, startDate, endDate])

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
  const rentalAmount = durationDays * rentalPrice
  const totalAmount = rentalAmount + deposit

  // Preserve state URL for navigating to Address page and returning
  const editAddressUrl = `/my-address?returnTo=${encodeURIComponent(
    `/request-booking/${id}?start_date=${startDate}&end_date=${endDate}`
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

    if (durationDays <= 0) {
      setError('Please select valid rental dates. End date must be after start date.')
      return
    }

    if (!isAddressComplete(userAddress)) {
      setError('Please complete your address before booking.')
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

  const hasCompleteAddress = isAddressComplete(userAddress)

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

                <form onSubmit={handleSubmit} className="mt-6 space-y-6">
                  {/* STEP 1: DATE SELECTION & AVAILABILITY */}
                  <div className="rounded-2xl border border-orange-200/80 bg-[#FFFDFB] p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-bold text-[#352720] flex items-center gap-2">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#D97745] text-white text-[11px] font-bold">
                          1
                        </span>
                        <Calendar size={16} className="text-[#D97745]" />
                        Select Rental Dates
                      </h2>

                      {checkingAvailability ? (
                        <span className="inline-flex items-center text-xs text-gray-500 animate-pulse">
                          Checking availability...
                        </span>
                      ) : effectiveAvailability?.is_available ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Available for selected dates
                        </span>
                      ) : effectiveAvailability && !effectiveAvailability.is_available ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-bold text-[#D97745] border border-amber-200">
                          <span className="h-1.5 w-1.5 rounded-full bg-[#D97745]" />
                          Booked for selected dates
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

                  {/* STEP 2: MANDATORY ADDRESS CONFIRMATION */}
                  <div className="rounded-2xl border border-orange-200/80 bg-[#FFFDFB] p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-bold text-[#352720] flex items-center gap-2">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#D97745] text-white text-[11px] font-bold">
                          2
                        </span>
                        <MapPin size={16} className="text-[#D97745]" />
                        Confirm Your Address
                      </h2>

                      {hasCompleteAddress && (
                        <Link
                          to={editAddressUrl}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-[#D97745] hover:underline"
                        >
                          <Edit2 size={12} /> Change Address
                        </Link>
                      )}
                    </div>

                    {loadingAddress ? (
                      <div className="h-16 bg-white rounded-xl border border-orange-100 animate-pulse" />
                    ) : hasCompleteAddress ? (
                      <div className="rounded-xl border border-orange-100 bg-white p-4 text-xs space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-[#352720] text-sm">
                            {userAddress.full_name}
                          </span>
                          <span className="rounded bg-[#FFF0E7] px-2 py-0.5 text-[10px] font-bold text-[#D97745] uppercase">
                            {userAddress.address_type || 'Saved Address'}
                          </span>
                        </div>
                        <p className="text-gray-600 leading-relaxed">
                          {[userAddress.house_number, userAddress.address, userAddress.area].filter(Boolean).join(', ')}
                        </p>
                        <p className="text-gray-800 font-medium">
                          {[userAddress.city, userAddress.state, userAddress.pincode].filter(Boolean).join(', ')}
                        </p>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50/70 p-4 text-xs space-y-2">
                        <div className="flex items-start gap-2 text-amber-900 font-semibold">
                          <AlertCircle size={15} className="text-[#D97745] shrink-0 mt-0.5" />
                          <span>Please complete your address before booking.</span>
                        </div>
                        <p className="text-gray-600 text-[11px] pl-6">
                          A complete address with house number, street, city, and PIN code is required to submit a booking request.
                        </p>
                        <div className="pt-1 pl-6">
                          <Link
                            to={editAddressUrl}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-[#D97745] px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-[#B85D32] transition"
                          >
                            <Plus size={14} /> Add / Complete Address
                          </Link>
                        </div>
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
                      <div className="flex justify-between items-center text-gray-600">
                        <span>Rental Duration:</span>
                        <span className="font-semibold text-[#352720]">
                          {durationDays} {durationDays === 1 ? 'day' : 'days'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center text-gray-600">
                        <span>Rental Fee ({durationDays} × ₹{rentalPrice}):</span>
                        <span className="font-semibold text-[#352720]">₹{rentalAmount.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between items-center text-gray-600">
                        <span className="inline-flex items-center gap-1">
                          <ShieldCheck size={13} className="text-emerald-600" /> Security Deposit (Refundable):
                        </span>
                        <span className="font-semibold text-[#352720]">₹{deposit.toFixed(2)}</span>
                      </div>
                      <div className="pt-2 border-t border-orange-50 flex justify-between items-baseline font-bold">
                        <span className="text-sm text-[#352720]">Total Amount:</span>
                        <span className="text-lg text-[#9D4C29]">₹{totalAmount.toFixed(2)}</span>
                      </div>
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
                        submitting ||
                        durationDays <= 0 ||
                        !hasCompleteAddress ||
                        (effectiveAvailability && !effectiveAvailability.is_available)
                      }
                      className="inline-flex items-center gap-2 rounded-xl bg-[#9D4C29] px-6 py-2.5 text-xs font-semibold text-white hover:bg-[#813B20] transition disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                    >
                      {submitting
                        ? 'Submitting Request...'
                        : !hasCompleteAddress
                        ? 'Complete Address to Book'
                        : effectiveAvailability && !effectiveAvailability.is_available
                        ? 'Dates Unavailable'
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
