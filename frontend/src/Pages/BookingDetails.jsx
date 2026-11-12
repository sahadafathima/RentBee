import useCurrentUserId from '../hooks/useCurrentUserId'
import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import CancelBookingModal from '../Components/CancelBookingModal'
import { getBookingDetails, cancelBooking } from '../services/api'
import {
  ChevronRight,
  ArrowLeft,
  Calendar,
  Clock,
  ShieldCheck,
  UserCheck,
  Phone,
  MapPin,
  Navigation,
  Lock,
  ExternalLink,
  Package,
  AlertTriangle,
  Info,
  CheckCircle2,
  Hourglass,
} from 'lucide-react'
import { formatKolkataDateTime, calculateReturnCountdown } from '../utils/dateUtils'

export default function BookingDetails() {
  const { id } = useParams()
  const viewerId = useCurrentUserId()
  const [booking, setBooking] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Geolocation & Navigation State
  const [userLocation, setUserLocation] = useState(null)
  const [locating, setLocating] = useState(false)
  const [locationError, setLocationError] = useState(null)

  // Cancel modal state
  const [cancelModalOpen, setCancelModalOpen] = useState(false)
  const [cancelling, setCancelling] = useState(false)

  // Real-time Return Countdown
  const [countdown, setCountdown] = useState({
    isValid: false,
    isOverdue: false,
    text: '',
    days: 0,
    hours: 0,
    minutes: 0,
    seconds: 0,
  })

  useEffect(() => {
    if (!booking?.return_deadline || booking.status !== 'rental_in_progress') {
      return
    }
    const updateCountdown = () => {
      setCountdown(calculateReturnCountdown(booking.return_deadline))
    }
    updateCountdown()
    const timer = setInterval(updateCountdown, 1000)
    return () => clearInterval(timer)
  }, [booking?.return_deadline, booking?.status])

  const reloadDetails = () => {
    setLoading(true)
    setError(null)
    getBookingDetails(id)
      .then((data) => {
        setBooking(data)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message || 'Failed to load booking details.')
        setLoading(false)
      })
  }

  useEffect(() => {
    let isCurrent = true
    getBookingDetails(id)
      .then((data) => {
        if (isCurrent) {
          setBooking(data)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (isCurrent) {
          setError(err.message || 'Failed to load booking details.')
          setLoading(false)
        }
      })

    return () => {
      isCurrent = false
    }
  }, [id])

  // Explicit user action for location permission
  const handleRequestLocation = () => {
    if (!navigator.geolocation) {
      setLocationError('Geolocation is not supported by your browser.')
      return
    }

    setLocating(true)
    setLocationError(null)

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        })
        setLocating(false)
      },
      (err) => {
        console.warn('Geolocation denied or failed:', err)
        setLocationError(
          'Location permission was denied. You can still use the pickup address below to navigate manually.'
        )
        setLocating(false)
      },
      { timeout: 10000, enableHighAccuracy: true }
    )
  }

  const handleConfirmCancel = async (bookingId, reason) => {
    setCancelling(true)
    try {
      await cancelBooking(bookingId, reason)
      setCancelModalOpen(false)
      reloadDetails()
    } catch (err) {
      alert(err.message || 'Failed to cancel booking.')
    } finally {
      setCancelling(false)
    }
  }

  const getStatusBadge = (status) => {
    switch (status) {
      case 'pending_approval':
        return {
          label: 'Waiting for Owner Approval',
          color: 'bg-amber-50 text-amber-800 border-amber-200',
        }
      case 'waiting_for_pickup':
        return {
          label: 'Waiting for Pickup',
          color: 'bg-orange-50 text-[#9D4C29] border-orange-200',
        }
      case 'rental_in_progress':
        return {
          label: 'Rental in Progress',
          color: 'bg-blue-50 text-blue-800 border-blue-200',
        }
      case 'completed':
        return {
          label: 'Completed',
          color: 'bg-emerald-50 text-emerald-800 border-emerald-200',
        }
      case 'rejected':
        return {
          label: 'Declined by Owner',
          color: 'bg-gray-100 text-gray-700 border-gray-300',
        }
      case 'expired':
        return {
          label: 'Request Expired',
          color: 'bg-slate-100 text-slate-700 border-slate-300',
        }
      case 'cancelled':
      default:
        return {
          label: 'Cancelled by You',
          color: 'bg-rose-50 text-rose-800 border-rose-200',
        }
    }
  }

  return (
    <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
      <div>
        <Navbar />

        <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
          
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
                <Link to="/bookings" className="hover:text-[#D97745] transition">
                  My Bookings
                </Link>
              </li>
              <li>
                <ChevronRight size={13} className="text-gray-400" />
              </li>
              <li className="font-semibold text-[#352720]">
                {booking ? booking.booking_reference : 'Booking Details'}
              </li>
            </ol>
          </nav>

          {/* Loading State */}
          {loading && (
            <div className="space-y-6 animate-pulse">
              <div className="h-10 w-1/3 bg-orange-100/60 rounded-2xl" />
              <div className="h-64 rounded-3xl bg-white border border-orange-100 p-6" />
              <div className="h-48 rounded-3xl bg-white border border-orange-100 p-6" />
            </div>
          )}

          {/* Error State */}
          {!loading && error && (
            <div className="rounded-3xl border border-rose-200 bg-white p-8 text-center shadow-xs">
              <AlertTriangle size={32} className="mx-auto text-rose-500" />
              <h2 className="mt-3 text-lg font-bold text-[#352720]">Cannot Access Booking</h2>
              <p className="mt-1 text-xs text-gray-500">{error}</p>
              <Link
                to="/bookings"
                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#D97745] px-4 py-2 text-xs font-semibold text-white"
              >
                <ArrowLeft size={14} /> Back to My Bookings
              </Link>
            </div>
          )}

          {/* Main Booking Content */}
          {!loading && booking && (
            <div className="space-y-6">
              
              {/* Top Banner / Status Overview */}
              <div className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="font-semibold uppercase tracking-wider text-[#D97745]">
                      {booking.item?.category_name}
                    </span>
                    <span className="text-gray-300">•</span>
                    <span className="font-mono font-medium text-gray-500">
                      {booking.booking_reference}
                    </span>
                  </div>
                  <h1 className="mt-1 text-xl sm:text-2xl font-black text-[#352720]">
                    {booking.item?.name}
                  </h1>
                </div>

                <div className="flex flex-wrap items-center gap-2 sm:self-center">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-bold ${
                      getStatusBadge(booking.status).color
                    }`}
                  >
                    {getStatusBadge(booking.status).label}
                  </span>

                  {booking.can_cancel && (
                    <button
                      type="button"
                      onClick={() => setCancelModalOpen(true)}
                      className="rounded-xl border border-rose-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 transition"
                    >
                      Cancel Booking
                    </button>
                  )}

                  {booking.can_report_problem && (
                    <Link
                      to={`/report-problem/${booking.id}`}
                      className="rounded-xl bg-[#D97745] px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-[#B85D32] transition"
                    >
                      Report Any Problem
                    </Link>
                  )}

                  {booking.renter?.id === viewerId && booking.status === 'completed' && (
                    <Link
                      to={`/request-booking/${booking.item?.id}`}
                      className="rounded-xl bg-[#9D4C29] px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-[#813B20] transition"
                    >
                      Book Again
                    </Link>
                  )}
                </div>
              </div>

              {/* Rejection Notice Banner */}
              {booking.status === 'rejected' && (
                <div className="rounded-3xl border border-rose-200 bg-rose-50/70 p-5 shadow-xs">
                  <div className="flex items-start gap-3">
                    <AlertTriangle size={20} className="text-rose-600 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <h3 className="font-bold text-rose-950 text-sm">
                        Booking Request Declined by Owner
                      </h3>
                      <p className="text-xs text-rose-800 leading-relaxed">
                        {booking.rejection_reason ? (
                          <>
                            <span className="font-semibold text-rose-900">Reason provided: </span>
                            {booking.rejection_reason}
                          </>
                        ) : (
                          'The owner was unable to accommodate this rental request.'
                        )}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Grid: Rental Item Details & Pricing Breakdown */}
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                
                {/* Left 2 Cols: Item Details */}
                <div className="lg:col-span-2 space-y-6">
                  
                  {/* Item Summary Card */}
                  <div className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                    <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29] mb-4 flex items-center gap-2">
                      <Package size={16} />
                      Rental Item Overview
                    </h2>

                    <div className="flex flex-col sm:flex-row gap-5">
                      <div className="h-40 w-40 shrink-0 overflow-hidden rounded-2xl bg-orange-50 border border-orange-100 self-center sm:self-start">
                        {booking.item?.primary_image_url ? (
                          <img
                            src={booking.item.primary_image_url}
                            alt={booking.item.name}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <div className="flex h-full w-full items-center justify-center text-orange-300">
                            <Package size={44} />
                          </div>
                        )}
                      </div>

                      <div className="flex-1 space-y-2 text-xs">
                        <p className="text-gray-600 leading-relaxed">
                          {booking.item?.description || 'No detailed description provided.'}
                        </p>

                        {booking.item?.rental_kit && booking.item.rental_kit.length > 0 && (
                          <div className="pt-2">
                            <span className="font-semibold text-[#352720]">Rental Kit Includes:</span>
                            <div className="mt-1 flex flex-wrap gap-1.5">
                              {booking.item.rental_kit.map((kitItem, i) => (
                                <span
                                  key={i}
                                  className="rounded-lg bg-orange-50 border border-orange-100 px-2 py-0.5 text-[11px] font-medium text-[#49362D]"
                                >
                                  {kitItem}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="pt-3 border-t border-orange-100 flex flex-wrap gap-4 text-xs text-gray-600">
                          <div className="flex items-center gap-1.5">
                            <Calendar size={14} className="text-[#D97745]" />
                            <span>
                              {booking.start_date} → {booking.end_date}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 font-bold text-[#9D4C29]">
                            <Clock size={14} />
                            <span>
                              {booking.duration_days} {booking.duration_days === 1 ? 'day' : 'days'}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Rental Schedule & Exact Return Deadline Card */}
                  <div className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                    <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29] mb-4 flex items-center gap-2">
                      <Clock size={16} />
                      Rental Schedule & Return Deadline
                    </h2>

                    {booking.status === 'rental_in_progress' ? (
                      booking.return_deadline && countdown.isValid ? (
                        <div className="space-y-4">
                          {/* Return Deadline Highlight Box */}
                          <div className="rounded-2xl bg-[#FFF9F5] border border-orange-200/80 p-4 sm:p-5">
                            <span className="text-[11px] font-bold uppercase tracking-wider text-[#D97745] block mb-1">
                              Exact Return Deadline (Asia/Kolkata IST)
                            </span>
                            <div className="text-lg sm:text-2xl font-black text-[#352720]">
                              {booking.return_deadline_display || formatKolkataDateTime(booking.return_deadline)}
                            </div>
                            <div className="mt-2 pt-2 border-t border-orange-100/80 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
                              <div>
                                <span className="text-gray-400">Owner Confirmed Pickup:</span>{' '}
                                <strong className="text-[#352720]">
                                  {booking.picked_up_at_display || formatKolkataDateTime(booking.picked_up_at)}
                                </strong>
                              </div>
                              <div>
                                <span className="text-gray-400">Duration:</span>{' '}
                                <strong className="text-[#352720]">
                                  {booking.duration_days} {booking.duration_days === 1 ? 'day' : 'days'} ({booking.duration_days * 24} hours)
                                </strong>
                              </div>
                            </div>
                          </div>

                          {/* Live Countdown / Overdue Alert */}
                          {countdown.isOverdue ? (
                            <div className="rounded-2xl border border-rose-200 bg-rose-50/70 p-4 text-xs text-rose-950 flex items-start gap-3">
                              <AlertTriangle size={18} className="text-rose-600 shrink-0 mt-0.5" />
                              <div className="space-y-1">
                                <h3 className="font-bold text-sm text-rose-900">
                                  Return Deadline Has Passed
                                </h3>
                                <p className="font-semibold text-rose-700">
                                  {countdown.text}
                                </p>
                                <p className="text-gray-600 leading-relaxed pt-1">
                                  The 24-hour rental periods have concluded. Please return the equipment to the owner as soon as possible. The rental remains active in the system until the owner verifies the item condition and confirms return.
                                </p>
                              </div>
                            </div>
                          ) : (
                            <div className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-4 text-xs text-emerald-950 flex items-start gap-3">
                              <Hourglass size={18} className="text-emerald-600 shrink-0 mt-0.5 animate-pulse" />
                              <div className="space-y-1 flex-1">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <h3 className="font-bold text-sm text-emerald-900">
                                    Rental Time Remaining
                                  </h3>
                                  <span className="rounded-full bg-emerald-100 border border-emerald-200 px-2.5 py-0.5 text-[11px] font-bold text-emerald-800">
                                    Active Countdown
                                  </span>
                                </div>
                                <div className="text-base sm:text-lg font-black text-emerald-800">
                                  {countdown.days > 0 ? `${countdown.days}d ` : ''}
                                  {countdown.hours}h {countdown.minutes}m {countdown.seconds}s
                                </div>
                                <p className="text-gray-500 text-[11px] leading-relaxed">
                                  Countdown is computed strictly from owner pickup confirmation time in 24-hour cycles.
                                </p>
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="rounded-2xl bg-amber-50/70 border border-amber-200 p-4 text-xs text-amber-900 space-y-1">
                          <div className="flex items-center gap-1.5 font-bold text-amber-950">
                            <Clock size={14} className="text-amber-700" />
                            <span>Pickup Confirmation Timestamp Not Recorded</span>
                          </div>
                          <p className="text-amber-800 leading-relaxed">
                            This rental is in progress, but does not have a recorded owner handover timestamp. Countdown and deadline require an actual pickup confirmation timestamp.
                          </p>
                          <p className="text-gray-600 pt-1">
                            Scheduled dates: <strong>{booking.start_date} → {booking.end_date}</strong> ({booking.duration_days} {booking.duration_days === 1 ? 'day' : 'days'})
                          </p>
                        </div>
                      )
                    ) : booking.status === 'completed' ? (
                      <div className="rounded-2xl bg-emerald-50/60 border border-emerald-200 p-4 text-xs text-emerald-950 space-y-2">
                        <div className="flex items-center gap-2 text-emerald-800 font-bold text-sm">
                          <CheckCircle2 size={16} />
                          <span>Rental Completed Successfully</span>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 border-t border-emerald-100 text-gray-700">
                          <div>
                            <span className="text-gray-400 block text-[11px]">Owner Pickup Handover:</span>
                            <span className="font-semibold text-[#352720]">
                              {booking.picked_up_at_display || formatKolkataDateTime(booking.picked_up_at) || 'Recorded'}
                            </span>
                          </div>
                          <div>
                            <span className="text-gray-400 block text-[11px]">Return Deadline:</span>
                            <span className="font-semibold text-[#352720]">
                              {booking.return_deadline_display || formatKolkataDateTime(booking.return_deadline) || 'Recorded'}
                            </span>
                          </div>
                          <div>
                            <span className="text-gray-400 block text-[11px]">Returned & Confirmed:</span>
                            <span className="font-semibold text-[#352720]">
                              {booking.returned_at_display || formatKolkataDateTime(booking.returned_at) || 'Recorded'}
                            </span>
                          </div>
                        </div>
                      </div>
                    ) : booking.status === 'waiting_for_pickup' ? (
                      <div className="rounded-2xl bg-orange-50/60 border border-orange-200 p-4 text-xs text-[#49362D] space-y-2">
                        <div className="flex items-center gap-2 text-[#9D4C29] font-bold text-sm">
                          <Clock size={16} />
                          <span>Awaiting Owner Handover Confirmation</span>
                        </div>
                        <p className="leading-relaxed text-gray-600">
                          Scheduled Dates: <strong>{booking.start_date} → {booking.end_date}</strong> ({booking.duration_days} {booking.duration_days === 1 ? 'day' : 'days'}).
                        </p>
                        <p className="text-[11px] text-gray-500 pt-1 border-t border-orange-100">
                          The exact return deadline will be stamped the moment the owner confirms physical item pickup ({booking.duration_days} × 24-hour periods from handover).
                        </p>
                      </div>
                    ) : booking.status === 'rejected' ? (
                      <div className="rounded-2xl bg-rose-50/60 border border-rose-200 p-4 text-xs text-rose-950 space-y-2">
                        <div className="flex items-center gap-2 text-rose-800 font-bold text-sm">
                          <AlertTriangle size={16} />
                          <span>Booking Request Declined</span>
                        </div>
                        <p className="leading-relaxed text-gray-600">
                          This booking request was declined by the owner and did not proceed to rental.
                        </p>
                        {booking.rejection_reason && (
                          <div className="pt-2 border-t border-rose-100 text-xs">
                            <span className="text-rose-800 font-semibold block">Reason for Rejection:</span>
                            <span className="text-[#352720] mt-0.5 block">{booking.rejection_reason}</span>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="rounded-2xl bg-gray-50 border border-gray-200 p-4 text-xs text-gray-600 space-y-1">
                        <p>
                          Booked Duration: <strong>{booking.duration_days} {booking.duration_days === 1 ? 'day' : 'days'}</strong> ({booking.start_date} → {booking.end_date})
                        </p>
                        <p className="text-gray-400 text-[11px]">
                          Rental countdown is activated upon owner handover confirmation.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Owner & Pickup Details (Privacy Protected) */}
                  <div className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                    <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29] mb-4 flex items-center gap-2">
                      <UserCheck size={16} />
                      Owner & Pickup Location
                    </h2>

                    {booking.owner?.address_info?.is_redacted ? (
                      /* Redacted Notice for pending_approval */
                      <div className="rounded-2xl bg-amber-50/70 border border-amber-200/80 p-5 text-xs text-amber-900">
                        <div className="flex items-start gap-3">
                          <Lock size={18} className="text-amber-600 shrink-0 mt-0.5" />
                          <div>
                            <h3 className="font-bold text-amber-950 text-sm">
                              Address & Contact Privacy Notice
                            </h3>
                            <p className="mt-1 leading-relaxed">
                              {booking.owner.address_info.notice}
                            </p>
                            <p className="mt-2 text-amber-800">
                              General Locality: <span className="font-semibold">{booking.owner.address_info.locality || 'Nearby'}, {booking.owner.address_info.city || 'Local area'}</span>
                            </p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      /* Confirmed stages: Full Owner Address & Contact Details */
                      <div className="space-y-4">
                        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-[#FFF9F5] border border-orange-100 p-4">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-[#352720] text-sm">
                                {booking.owner?.full_name}
                              </span>
                              {booking.owner?.is_verified && (
                                <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-semibold text-[#D97745]">
                                  <ShieldCheck size={12} /> Verified Lender
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-xs text-gray-500">
                              Registered Equipment Owner
                            </p>
                          </div>

                          {booking.owner?.phone_number && (
                            <a
                              href={`tel:${booking.owner.phone_number}`}
                              className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-emerald-700 transition"
                            >
                              <Phone size={14} /> Call Owner ({booking.owner.phone_number})
                            </a>
                          )}
                        </div>

                        {/* Registered Pickup Address */}
                        <div className="rounded-2xl border border-orange-100 bg-white p-4 text-xs text-[#49362D] space-y-2">
                          <div className="flex items-start gap-2.5">
                            <MapPin size={16} className="text-[#D97745] shrink-0 mt-0.5" />
                            <div>
                              <strong className="text-[#352720]">Pickup Address:</strong>
                              <p className="mt-1 text-gray-600 leading-relaxed font-medium">
                                {booking.owner?.address_info?.full_formatted_address}
                              </p>
                              {booking.owner?.address_info?.landmark && (
                                <p className="mt-1 text-xs text-gray-500">
                                  Landmark: {booking.owner.address_info.landmark}
                                </p>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Google Maps Interactive Navigation Section */}
                        <div className="rounded-2xl border border-orange-200 bg-[#FFFDFB] p-5">
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2 text-sm font-bold text-[#352720]">
                              <Navigation size={17} className="text-[#D97745]" />
                              <span>Route to Pickup Address</span>
                            </div>

                            <a
                              href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(
                                booking.owner?.address_info?.full_formatted_address || ''
                              )}${
                                userLocation
                                  ? `&origin=${userLocation.lat},${userLocation.lng}`
                                  : ''
                              }`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#D97745] hover:text-[#9D4C29] transition"
                            >
                              <span>Open in Google Maps</span>
                              <ExternalLink size={13} />
                            </a>
                          </div>

                          <p className="text-xs text-gray-600 mb-4 leading-relaxed">
                            Need turn-by-turn navigation? Click below to request location permission and calculate directions from your current location to the owner's pickup point.
                          </p>

                          {!userLocation ? (
                            <button
                              type="button"
                              onClick={handleRequestLocation}
                              disabled={locating}
                              className="inline-flex items-center gap-2 rounded-xl bg-[#D97745] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[#B85D32] transition disabled:opacity-50"
                            >
                              <Navigation size={14} />
                              {locating ? 'Requesting GPS Location...' : 'Use My Current Location'}
                            </button>
                          ) : (
                            <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3 text-xs text-emerald-800 flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <CheckCircle2 size={16} className="text-emerald-600" />
                                <span>
                                  Location acquired! Coordinates: {userLocation.lat.toFixed(4)}, {userLocation.lng.toFixed(4)}
                                </span>
                              </div>
                              <a
                                href={`https://www.google.com/maps/dir/?api=1&origin=${userLocation.lat},${userLocation.lng}&destination=${encodeURIComponent(
                                  booking.owner?.address_info?.full_formatted_address || ''
                                )}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="font-bold underline"
                              >
                                Start Navigation
                              </a>
                            </div>
                          )}

                          {locationError && (
                            <p className="mt-2 text-xs text-rose-600 font-medium">
                              {locationError}
                            </p>
                          )}
                        </div>

                      </div>
                    )}
                  </div>

                </div>

                {/* Right Col: Pricing & Security Deposit Breakdown */}
                <div className="space-y-6">
                  
                  <div className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                    <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29] mb-4">
                      Rental Pricing Breakdown
                    </h2>

                    <div className="space-y-3 text-xs">
                      <div className="flex justify-between items-center text-gray-600">
                        <span>Daily Rental Rate:</span>
                        <span className="font-semibold text-[#352720]">₹{booking.daily_price} / day</span>
                      </div>

                      <div className="flex justify-between items-center text-gray-600">
                        <span>Rental Duration:</span>
                        <span className="font-semibold text-[#352720]">{booking.duration_days} {booking.duration_days === 1 ? 'day' : 'days'}</span>
                      </div>
                      <div className="flex justify-between items-center text-gray-600">
                        <span>Requested Quantity:</span>
                        <span className="font-semibold text-[#352720]">{booking.requested_quantity || 1} unit{(booking.requested_quantity || 1) === 1 ? '' : 's'}</span>
                      </div>

                      <div className="flex justify-between items-center text-gray-600">
                        <span>Total Rental Fee:</span>
                        <span className="font-semibold text-[#352720]">₹{booking.rental_amount}</span>
                      </div>

                      <div className="flex justify-between items-center text-gray-600">
                        <span>Security Deposit (Refundable):</span>
                        <span className="font-semibold text-[#352720]">₹{booking.deposit_amount}</span>
                      </div>

                      <div className="pt-3 border-t border-orange-100 flex justify-between items-baseline">
                        <span className="text-sm font-bold text-[#352720]">Total Amount:</span>
                        <span className="text-xl font-black text-[#9D4C29]">₹{booking.total_amount}</span>
                      </div>

                      <div className="mt-4 pt-4 border-t border-orange-50">
                        <div className="flex items-center justify-between">
                          <span className="text-gray-500 font-medium">Payment Status:</span>
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                              booking.payment_status === 'paid'
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            {booking.payment_status_display}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Safety & Cancellation Guidelines */}
                  <div className="rounded-3xl border border-orange-100 bg-[#FFFDFB] p-5 text-xs text-gray-500 space-y-3">
                    <div className="flex items-start gap-2">
                      <Info size={16} className="text-[#D97745] shrink-0 mt-0.5" />
                      <p>
                        Cancellation is only permitted prior to owner pickup confirmation. Once handed over, the rental is in progress.
                      </p>
                    </div>

                    <div className="flex items-start gap-2">
                      <ShieldCheck size={16} className="text-emerald-600 shrink-0 mt-0.5" />
                      <p>
                        Security deposits are safely verified and refunded upon successful item inspection and return confirmation.
                      </p>
                    </div>
                  </div>

                </div>

              </div>

            </div>
          )}

        </main>
      </div>

      <Footer />

      {/* Cancel Modal */}
      <CancelBookingModal
        booking={booking}
        isOpen={cancelModalOpen}
        onClose={() => setCancelModalOpen(false)}
        onConfirm={handleConfirmCancel}
        loading={cancelling}
      />
    </div>
  )
}
