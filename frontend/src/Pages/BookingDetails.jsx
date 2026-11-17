import useCurrentUserId from '../hooks/useCurrentUserId'
import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import CancelBookingModal from '../Components/CancelBookingModal'
import PickupOtpModal from '../Components/PickupOtpModal'
import ReturnCountdownTimer from '../Components/ReturnCountdownTimer'
import {
  getBookingDetails,
  cancelBooking,
  retryBookingRefund,
  confirmOfflineRefund,
  createPaymentOrder,
  verifyPayment,
  confirmOfflineBookingPayment,
  confirmReturn,
  downloadBookingInvoice,
} from '../services/api'
import { loadRazorpayScript } from '../utils/razorpay'
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
  CreditCard,
  Banknote,
  FileText,
  Tag,
  RefreshCcw,
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

  // Payment state
  const [paying, setPaying] = useState(false)
  const [confirmingOffline, setConfirmingOffline] = useState(false)
  const [confirmingReturn, setConfirmingReturn] = useState(false)
  const [otpModalOpen, setOtpModalOpen] = useState(false)
  const [paymentError, setPaymentError] = useState(null)
  const [paymentSuccess, setPaymentSuccess] = useState(false)
  const [downloadingInvoice, setDownloadingInvoice] = useState(false)
  const [downloadInvoiceError, setDownloadInvoiceError] = useState(null)

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

    const fetchBookingSilently = () => {
      getBookingDetails(id)
        .then((data) => {
          if (isCurrent) {
            setBooking(data)
          }
        })
        .catch(() => {})
    }

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

    const onEvent = () => fetchBookingSilently()
    window.addEventListener('focus', onEvent)
    window.addEventListener('rentbee:bookings-changed', onEvent)
    document.addEventListener('visibilitychange', onEvent)

    // While awaiting pickup confirmation or pending approval, periodically poll so handover transitions seamlessly
    let pollInterval = null
    if (booking?.status === 'waiting_for_pickup' || booking?.status === 'pending_approval') {
      pollInterval = setInterval(fetchBookingSilently, 5000)
    }

    return () => {
      isCurrent = false
      window.removeEventListener('focus', onEvent)
      window.removeEventListener('rentbee:bookings-changed', onEvent)
      document.removeEventListener('visibilitychange', onEvent)
      if (pollInterval) clearInterval(pollInterval)
    }
  }, [id, booking?.status])

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

  const [retryingRefund, setRetryingRefund] = useState(false)
  const [confirmingCashRefund, setConfirmingCashRefund] = useState(false)

  const handleConfirmCancel = async (bookingId, reason) => {
    setCancelling(true)
    try {
      const res = await cancelBooking(bookingId, reason)
      setCancelModalOpen(false)
      if (res?.booking) {
        setBooking(res.booking)
      } else {
        reloadDetails()
      }
    } catch (err) {
      alert(err.message || 'Failed to cancel booking.')
    } finally {
      setCancelling(false)
    }
  }

  const handleRetryRefund = async () => {
    setRetryingRefund(true)
    try {
      const res = await retryBookingRefund(booking.id)
      if (res?.booking) {
        setBooking(res.booking)
      } else {
        reloadDetails()
      }
    } catch (err) {
      alert(err.message || 'Failed to retry refund.')
    } finally {
      setRetryingRefund(false)
    }
  }

  const handleConfirmOfflineRefund = async () => {
    if (!window.confirm(`Confirm that you have returned ₹${booking.total_amount} in cash to the renter?`)) {
      return
    }
    setConfirmingCashRefund(true)
    try {
      const res = await confirmOfflineRefund(booking.id)
      if (res?.booking) {
        setBooking(res.booking)
      } else {
        reloadDetails()
      }
    } catch (err) {
      alert(err.message || 'Failed to confirm cash refund.')
    } finally {
      setConfirmingCashRefund(false)
    }
  }

  const handlePayNow = async () => {
    setPaying(true)
    setPaymentError(null)
    setPaymentSuccess(false)
    try {
      const isLoaded = await loadRazorpayScript()
      if (!isLoaded) {
        throw new Error('Failed to load Razorpay payment gateway. Please check your network connection.')
      }

      const orderData = await createPaymentOrder(booking.id)

      const options = {
        key: orderData.key_id || '',
        amount: orderData.amount,
        currency: orderData.currency || 'INR',
        name: 'RentBee',
        description: `Rental payment for ${orderData.item_name || booking.item?.name || 'Item'} (${orderData.booking_reference})`,
        order_id: orderData.order_id,
        prefill: {
          name: orderData.prefill?.name || '',
          email: orderData.prefill?.email || '',
          contact: orderData.prefill?.contact || '',
        },
        theme: {
          color: '#D97745',
        },
        handler: async function (response) {
          try {
            setPaying(true)
            const verifyRes = await verifyPayment(booking.id, {
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            })
            if (verifyRes?.booking?.payment_status === 'paid') {
              setBooking(verifyRes.booking)
              setPaymentSuccess(true)
              setPaymentError(null)
            } else {
              const fresh = await getBookingDetails(booking.id)
              if (fresh?.payment_status === 'paid') {
                setBooking(fresh)
                setPaymentSuccess(true)
                setPaymentError(null)
              } else {
                setPaymentSuccess(false)
                setPaymentError('Payment confirmation is pending. Please refresh if the amount was deducted.')
              }
            }
          } catch (err) {
            setPaymentSuccess(false)
            setPaymentError(err.message || 'Payment verification failed.')
          } finally {
            setPaying(false)
          }
        },
        modal: {
          ondismiss: function () {
            // Dismissing the popup preserves pending status. Does not mark as failed.
            setPaying(false)
          },
        },
      }

      const rzp = new window.Razorpay(options)
      rzp.on('payment.failed', function (response) {
        setPaymentError(response.error?.description || 'Payment was declined by the bank or gateway.')
        setPaying(false)
      })
      rzp.open()
    } catch (err) {
      setPaymentError(err.message || 'Failed to initiate payment.')
      setPaying(false)
    }
  }

  const handleConfirmOfflinePayment = async () => {
    if (!window.confirm(`Confirm receipt of ₹${booking.total_amount} cash payment from the renter?`)) {
      return
    }
    setConfirmingOffline(true)
    setPaymentError(null)
    try {
      const res = await confirmOfflineBookingPayment(booking.id)
      if (res?.booking) {
        setBooking(res.booking)
      } else {
        reloadDetails()
      }
      setPaymentSuccess(true)
    } catch (err) {
      setPaymentError(err.message || 'Failed to confirm offline payment.')
    } finally {
      setConfirmingOffline(false)
    }
  }

  const handleDownloadInvoice = async () => {
    if (!booking?.id) return
    setDownloadingInvoice(true)
    setDownloadInvoiceError(null)
    try {
      await downloadBookingInvoice(booking.id, booking.booking_reference)
    } catch (err) {
      setDownloadInvoiceError(err.message || 'Failed to download invoice / receipt.')
    } finally {
      setDownloadingInvoice(false)
    }
  }

  const handleConfirmReturn = async () => {
    if (!window.confirm('Confirm that the rental item has been returned safely in good condition?')) {
      return
    }
    setConfirmingReturn(true)
    try {
      await confirmReturn(id)
      window.dispatchEvent(new Event('rentbee:bookings-changed'))
      reloadDetails()
    } catch (err) {
      alert(err.message || 'Failed to confirm return.')
    } finally {
      setConfirmingReturn(false)
    }
  }


  const canShowPayNow = Boolean(
    booking &&
    booking.payment_method === 'online' &&
    ['pending', 'failed'].includes(booking.payment_status) &&
    booking.status === 'waiting_for_pickup' &&
    booking.payment_status !== 'paid' &&
    (booking.can_pay ?? (viewerId && Number(booking.renter?.id) === Number(viewerId)))
  )

  const isOwner = Boolean(
    (viewerId && booking?.owner?.id && Number(viewerId) === Number(booking.owner.id)) ||
    booking?.can_confirm_offline_payment ||
    booking?.can_pickup ||
    booking?.can_return
  )

  const contactPerson = isOwner ? booking?.renter : booking?.owner
  const isContactRedacted = Boolean(contactPerson?.address_info?.is_redacted)
  const contactNotice = contactPerson?.address_info?.notice
  const contactLocality = contactPerson?.address_info?.locality
  const contactCity = contactPerson?.address_info?.city
  const contactPhone = contactPerson?.phone_number

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
          label: 'Rejected',
          color: 'bg-rose-50 text-rose-800 border-rose-200',
        }
      case 'expired':
        return {
          label: 'Request Expired',
          color: 'bg-slate-100 text-slate-700 border-slate-300',
        }
      case 'cancelled':
      default:
        if (booking?.payment_status === 'refunded' || booking?.refund_status === 'processed') {
          return {
            label: booking?.payment_method === 'offline' ? 'Cancelled & Cash Returned' : 'Cancelled & Refunded',
            color: 'bg-purple-50 text-purple-800 border-purple-200',
          }
        }
        if (booking?.refund_status === 'pending' || (booking?.payment_method === 'offline' && booking?.payment_status === 'paid')) {
          return {
            label: booking?.payment_method === 'offline' ? 'Cancelled (Cash Return Pending)' : 'Cancelled (Refund Processing)',
            color: 'bg-amber-50 text-amber-800 border-amber-200',
          }
        }
        if (booking?.refund_status === 'failed') {
          return {
            label: 'Cancelled (Refund Failed)',
            color: 'bg-rose-100 text-rose-900 border-rose-300',
          }
        }
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

                  {booking.can_confirm_offline_payment && (
                    <button
                      type="button"
                      onClick={handleConfirmOfflinePayment}
                      disabled={confirmingOffline}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 transition disabled:opacity-50 cursor-pointer"
                    >
                      <Banknote size={14} />
                      {confirmingOffline ? 'Confirming...' : 'Confirm Cash Payment'}
                    </button>
                  )}

                  {isOwner && booking.status === 'waiting_for_pickup' && booking.payment_status === 'paid' && (
                    <button
                      type="button"
                      onClick={() => setOtpModalOpen(true)}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-[#D97745] px-3.5 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-[#B85D32] transition cursor-pointer"
                    >
                      <ShieldCheck size={14} />
                      {booking.has_active_pickup_otp ? 'Verify Pickup OTP' : 'Send Pickup OTP'}
                    </button>
                  )}

                  {isOwner && booking.status === 'rental_in_progress' && (
                    <button
                      type="button"
                      onClick={handleConfirmReturn}
                      disabled={confirmingReturn}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-700 px-3.5 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-emerald-800 transition disabled:opacity-50 cursor-pointer"
                    >
                      {confirmingReturn ? 'Confirming...' : 'Confirm Return'}
                    </button>
                  )}

                  {booking.can_confirm_offline_refund && (
                    <button
                      type="button"
                      onClick={handleConfirmOfflineRefund}
                      disabled={confirmingCashRefund}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 transition disabled:opacity-50 cursor-pointer"
                    >
                      <Banknote size={14} />
                      {confirmingCashRefund ? 'Confirming...' : 'Confirm Cash Returned'}
                    </button>
                  )}

                  {booking.can_retry_refund && (
                    <button
                      type="button"
                      onClick={handleRetryRefund}
                      disabled={retryingRefund}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-amber-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-amber-700 transition disabled:opacity-50 cursor-pointer"
                    >
                      <RefreshCcw size={14} className={retryingRefund ? 'animate-spin' : ''} />
                      {retryingRefund ? 'Retrying...' : 'Retry Refund'}
                    </button>
                  )}

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
                <div className="rounded-3xl border border-rose-200 bg-rose-50/80 p-5 shadow-xs">
                  <div className="flex items-start gap-3">
                    <AlertTriangle size={20} className="text-rose-600 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <h3 className="font-bold text-rose-950 text-sm">
                        Booking Request Rejected
                      </h3>
                      <p className="text-xs text-rose-900 leading-relaxed">
                        <span className="font-semibold text-rose-950">Reason: </span>
                        <span>{booking.rejection_reason || 'The owner was unable to accommodate this rental request.'}</span>
                      </p>
                      {booking.rejected_at && (
                        <p className="text-[11px] text-rose-700">
                          Rejected on: {formatKolkataDateTime(booking.rejected_at)}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Cancellation & Refund Notice Banner */}
              {booking.status === 'cancelled' && (
                <div className="rounded-3xl border border-rose-200 bg-rose-50/70 p-5 shadow-xs space-y-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle size={20} className="text-rose-600 shrink-0 mt-0.5" />
                    <div className="space-y-1 flex-1">
                      <h3 className="font-bold text-rose-950 text-sm">
                        Booking Cancelled
                      </h3>
                      {booking.cancellation_reason && (
                        <p className="text-xs text-rose-900 leading-relaxed">
                          <span className="font-semibold text-rose-950">Cancellation Reason: </span>
                          <span>{booking.cancellation_reason}</span>
                        </p>
                      )}
                      {booking.cancelled_at && (
                        <p className="text-[11px] text-rose-700">
                          Cancelled on: {formatKolkataDateTime(booking.cancelled_at)}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Section 9: Online Payment Refund States */}
                  {booking.payment_method === 'online' && (booking.refund_status === 'pending' || (booking.payment_status === 'paid' && !['processed', 'failed'].includes(booking.refund_status))) && (
                    <div className="rounded-2xl border border-amber-200 bg-amber-50/90 p-4 text-xs text-amber-950 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-bold text-amber-900">
                          <Clock size={16} className="text-[#D97745]" />
                          <span>Refund Processing</span>
                        </div>
                        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-bold text-amber-800">
                          ₹{booking.refund_amount || booking.total_amount}
                        </span>
                      </div>
                      <p className="text-[11px] text-amber-900 leading-relaxed">
                        Razorpay has accepted the refund request and final processing is pending. 100% of the paid amount (₹{booking.refund_amount || booking.total_amount}) will be credited back to your original payment method. Bank clearance usually takes 5–7 business days.
                      </p>
                      {booking.refund_transaction_id && (
                        <p className="text-[10px] text-amber-800 font-mono">
                          Refund Reference: {booking.refund_transaction_id}
                        </p>
                      )}
                    </div>
                  )}

                  {(booking.payment_status === 'refunded' || booking.refund_status === 'processed') && booking.payment_method === 'online' && (
                    <div className="rounded-2xl border border-emerald-200 bg-emerald-50/90 p-4 text-xs text-emerald-950 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-bold text-emerald-900">
                          <CheckCircle2 size={16} className="text-emerald-600" />
                          <span>Refund Successful</span>
                        </div>
                        <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-bold text-emerald-800">
                          ₹{booking.refund_amount || booking.total_amount}
                        </span>
                      </div>
                      <p className="text-[11px] text-emerald-900 leading-relaxed">
                        100% of the paid amount (₹{booking.refund_amount || booking.total_amount}) has been successfully processed and refunded to your original payment method.
                      </p>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-emerald-800 pt-1">
                        {booking.refund_transaction_id && (
                          <span className="font-mono">Reference: {booking.refund_transaction_id}</span>
                        )}
                        {booking.refunded_at_display && (
                          <span>Completed on: {booking.refunded_at_display}</span>
                        )}
                      </div>
                    </div>
                  )}

                  {booking.payment_method === 'online' && booking.refund_status === 'failed' && (
                    <div className="rounded-2xl border border-rose-300 bg-rose-100/80 p-4 text-xs text-rose-950 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-bold text-rose-900">
                          <AlertTriangle size={16} className="text-rose-600" />
                          <span>Refund Failed</span>
                        </div>
                        <span className="rounded-full bg-rose-200 px-2.5 py-0.5 text-[11px] font-bold text-rose-900">
                          ₹{booking.refund_amount || booking.total_amount}
                        </span>
                      </div>
                      <p className="text-[11px] text-rose-900 leading-relaxed">
                        The refund could not be completed automatically by Razorpay. Please retry the refund or contact RentBee support for assistance.
                      </p>
                      {booking.refund_error && (
                        <p className="text-[10px] text-rose-800 font-mono">
                          Error: {booking.refund_error}
                        </p>
                      )}
                      {booking.can_retry_refund && (
                        <div className="pt-1">
                          <button
                            type="button"
                            onClick={handleRetryRefund}
                            disabled={retryingRefund}
                            className="inline-flex items-center gap-1.5 rounded-xl bg-rose-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-rose-800 transition disabled:opacity-50 cursor-pointer shadow-xs"
                          >
                            <RefreshCcw size={12} className={retryingRefund ? 'animate-spin' : ''} />
                            {retryingRefund ? 'Retrying Refund...' : 'Retry Refund Now'}
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Section 6: Offline Cash Return States */}
                  {booking.payment_method === 'offline' && booking.payment_status === 'paid' && !booking.cash_returned_at && (
                    <div className="rounded-2xl border border-amber-300 bg-amber-50/90 p-4 text-xs text-amber-950 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-bold text-amber-900">
                          <Banknote size={16} className="text-[#D97745]" />
                          <span>Cash Return Pending</span>
                        </div>
                        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-bold text-amber-800">
                          ₹{booking.refund_amount || booking.total_amount}
                        </span>
                      </div>
                      <p className="text-[11px] text-amber-900 leading-relaxed">
                        Cash payment was collected at pickup. Since the booking was cancelled before item handover, the host is required to return ₹{booking.total_amount} in cash directly to the renter.
                      </p>
                      {booking.can_confirm_offline_refund && (
                        <div className="pt-1">
                          <button
                            type="button"
                            onClick={handleConfirmOfflineRefund}
                            disabled={confirmingCashRefund}
                            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-700 transition disabled:opacity-50 cursor-pointer shadow-xs"
                          >
                            <Banknote size={12} />
                            {confirmingCashRefund ? 'Confirming...' : 'Confirm Cash Returned to Renter'}
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {booking.payment_method === 'offline' && (booking.payment_status === 'refunded' || booking.cash_returned_at) && (
                    <div className="rounded-2xl border border-emerald-200 bg-emerald-50/90 p-4 text-xs text-emerald-950 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-bold text-emerald-900">
                          <CheckCircle2 size={16} className="text-emerald-600" />
                          <span>Cash Return Completed</span>
                        </div>
                        <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-bold text-emerald-800">
                          ₹{booking.refund_amount || booking.total_amount}
                        </span>
                      </div>
                      <p className="text-[11px] text-emerald-900 leading-relaxed">
                        Full cash refund of ₹{booking.refund_amount || booking.total_amount} was confirmed returned by the host.
                      </p>
                      {booking.cash_returned_at_display && (
                        <p className="text-[10px] text-emerald-800">
                          Returned on: {booking.cash_returned_at_display}
                        </p>
                      )}
                    </div>
                  )}
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

                  {/* Shared Rental Schedule & Exact Return Deadline Countdown */}
                  <ReturnCountdownTimer booking={booking} />

                  {/* Owner & Pickup Details (Privacy Protected) */}
                  <div className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                    <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29] mb-4 flex items-center gap-2">
                      <UserCheck size={16} />
                      {isOwner ? 'User & Pickup Location' : 'Owner & Pickup Location'}
                    </h2>

                    {isContactRedacted ? (
                      /* Redacted Notice for pending_approval */
                      <div className="rounded-2xl bg-amber-50/70 border border-amber-200/80 p-5 text-xs text-amber-900">
                        <div className="flex items-start gap-3">
                          <Lock size={18} className="text-amber-600 shrink-0 mt-0.5" />
                          <div>
                            <h3 className="font-bold text-amber-950 text-sm">
                              Address & Contact Privacy Notice
                            </h3>
                            <p className="mt-1 leading-relaxed">
                              {contactNotice || 'Contact details are available only for approved, active, or completed bookings.'}
                            </p>
                            <p className="mt-2 text-amber-800">
                              General Locality: <span className="font-semibold">{contactLocality || 'Nearby'}, {contactCity || 'Local area'}</span>
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
                                {isOwner ? (booking.renter?.full_name || 'Renter') : booking.owner?.full_name}
                              </span>
                              {!isOwner && booking.owner?.is_verified && (
                                <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-semibold text-[#D97745]">
                                  <ShieldCheck size={12} /> Verified Lender
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-xs text-gray-500">
                              {isOwner ? 'Renter' : 'Registered Equipment Owner'}
                            </p>
                          </div>

                          {contactPhone && (
                            <a
                              href={`tel:${contactPhone}`}
                              className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-emerald-700 transition"
                            >
                              <Phone size={14} /> {isOwner ? 'Call User' : 'Call Owner'} ({contactPhone})
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

                  {/* Renter Delivery / Contact Address */}
                  {(() => {
                    const renterAddr = booking.renter_address || booking.renter?.address_info
                    if (!renterAddr || (!renterAddr.full_formatted_address && !renterAddr.city)) return null

                    const formatted = renterAddr.full_formatted_address || (
                      [renterAddr.house_number, renterAddr.address, renterAddr.area, renterAddr.city, renterAddr.state, renterAddr.pincode]
                        .filter(Boolean)
                        .join(', ')
                    )

                    return (
                      <div className="rounded-3xl border border-orange-100 bg-white p-6 shadow-xs">
                        <h2 className="text-sm font-bold uppercase tracking-wider text-[#9D4C29] mb-4 flex items-center gap-2">
                          <MapPin size={16} />
                          Delivery / Contact Address
                        </h2>

                        <div className="rounded-2xl border border-orange-100 bg-[#FFFDFB] p-4 text-xs text-[#49362D] space-y-2">
                          <div className="flex items-start justify-between gap-3">
                            <span className="font-bold text-[#352720] text-sm">
                              {renterAddr.full_name || booking.renter?.full_name || 'Renter'}
                            </span>
                            {renterAddr.address_type && (
                              <span className="rounded bg-[#FFF0E7] px-2 py-0.5 text-[10px] font-bold text-[#D97745] uppercase">
                                {renterAddr.address_type}
                              </span>
                            )}
                          </div>
                          <p className="text-gray-600 leading-relaxed font-medium">
                            {formatted}
                          </p>
                          {renterAddr.landmark && (
                            <p className="text-xs text-gray-500">
                              Landmark: {renterAddr.landmark}
                            </p>
                          )}
                        </div>
                      </div>
                    )
                  })()}

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
                        <span>{parseFloat(booking.discount_amount || 0) > 0 ? 'Original Rental Fee:' : 'Total Rental Fee:'}</span>
                        <span className={`font-semibold ${parseFloat(booking.discount_amount || 0) > 0 ? 'line-through text-gray-400' : 'text-[#352720]'}`}>
                          ₹{booking.original_rental_amount || (parseFloat(booking.rental_amount) + parseFloat(booking.discount_amount || 0)).toFixed(2)}
                        </span>
                      </div>

                      {parseFloat(booking.discount_amount || 0) > 0 && (
                        <>
                          <div className="flex justify-between items-center text-emerald-700 font-medium">
                            <span className="inline-flex items-center gap-1">
                              <Tag size={13} className="text-emerald-600" /> First Booking Discount (10%):
                            </span>
                            <span className="font-bold text-emerald-700">-₹{booking.discount_amount}</span>
                          </div>
                          <div className="flex justify-between items-center text-gray-600">
                            <span>Net Rental Fee:</span>
                            <span className="font-semibold text-[#352720]">₹{booking.rental_amount}</span>
                          </div>
                        </>
                      )}

                      <div className="flex justify-between items-center text-gray-600">
                        <span>Security Deposit (Refundable):</span>
                        <span className="font-semibold text-[#352720]">₹{booking.deposit_amount}</span>
                      </div>

                      <div className="pt-3 border-t border-orange-100 flex justify-between items-baseline">
                        <span className="text-sm font-bold text-[#352720]">Total Amount:</span>
                        <span className="text-xl font-black text-[#9D4C29]">₹{booking.total_amount}</span>
                      </div>

                      {/* Payment Section */}
                      <div className="mt-4 pt-4 border-t border-orange-100 space-y-3">
                        <div className="flex items-center justify-between">
                          <h3 className="text-xs font-bold uppercase tracking-wider text-[#9D4C29] flex items-center gap-1.5">
                            <CreditCard size={14} />
                            Payment
                          </h3>
                        </div>

                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-gray-500 font-medium">Payment Method:</span>
                            <span className="font-semibold text-[#352720] inline-flex items-center gap-1 text-[11px]">
                              {booking.payment_method === 'offline' ? (
                                <>
                                  <Banknote size={13} className="text-[#D97745]" />
                                  <span>{booking.payment_method_display || 'Pay at Pickup (Cash)'}</span>
                                </>
                              ) : (
                                <>
                                  <CreditCard size={13} className="text-[#D97745]" />
                                  <span>{booking.payment_method_display || 'Online Payment (Razorpay)'}</span>
                                </>
                              )}
                            </span>
                          </div>

                          {booking.status === 'rejected' ? (
                            <div className="flex items-center justify-between">
                              <span className="text-gray-500 font-medium">Payment Status:</span>
                              <span className="rounded-full px-2.5 py-0.5 text-[11px] font-bold bg-rose-100 text-rose-800">
                                Unavailable
                              </span>
                            </div>
                          ) : booking.status === 'cancelled' ? (
                            <div className="flex items-center justify-between">
                              <span className="text-gray-500 font-medium">Payment Status:</span>
                              <span
                                className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                                  booking.payment_status === 'refunded' || booking.refund_status === 'processed'
                                    ? 'bg-purple-100 text-purple-800'
                                    : booking.refund_status === 'failed'
                                    ? 'bg-rose-100 text-rose-800'
                                    : booking.refund_status === 'pending' || (booking.payment_method === 'offline' && booking.payment_status === 'paid')
                                    ? 'bg-amber-100 text-amber-800'
                                    : 'bg-slate-100 text-slate-700'
                                }`}
                              >
                                {booking.payment_status === 'refunded' || booking.refund_status === 'processed'
                                  ? (booking.payment_method === 'offline' ? 'Cash Returned' : 'Refund Successful')
                                  : booking.refund_status === 'failed'
                                  ? 'Refund Failed'
                                  : booking.refund_status === 'pending'
                                  ? (booking.payment_method === 'offline' ? 'Cash Return Pending' : 'Refund Processing')
                                  : booking.payment_status === 'paid'
                                  ? (booking.payment_method === 'offline' ? 'Cash Return Pending' : 'Refund Processing')
                                  : 'No Payment Required'}
                              </span>
                            </div>
                          ) : booking.status !== 'pending_approval' ? (
                            <div className="flex items-center justify-between">
                              <span className="text-gray-500 font-medium">Payment Status:</span>
                              <span
                                className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                                  booking.payment_status === 'paid'
                                    ? 'bg-emerald-100 text-emerald-800'
                                    : booking.payment_status === 'failed'
                                    ? 'bg-rose-100 text-rose-800'
                                    : 'bg-amber-100 text-amber-800'
                                }`}
                              >
                                {booking.payment_status_display}
                              </span>
                            </div>
                          ) : null}
                        </div>

                        {/* Pending Approval: Message before owner accepts */}
                        {booking.status === 'pending_approval' && (
                          <div className="rounded-2xl bg-amber-50/70 border border-amber-200/60 p-3 text-xs text-amber-800 flex items-start gap-2">
                            <Clock size={16} className="text-[#D97745] shrink-0 mt-0.5" />
                            <div className="text-[11px] leading-relaxed">
                              Payment will be available after the owner accepts your booking request.
                            </div>
                          </div>
                        )}

                        {/* Rejected: Show payment as unavailable and display rejection reason */}
                        {booking.status === 'rejected' && (
                          <div className="rounded-2xl bg-rose-50 border border-rose-200 p-3 text-xs text-rose-900 flex items-start gap-2">
                            <AlertTriangle size={15} className="text-rose-600 shrink-0 mt-0.5" />
                            <div className="flex-1 space-y-1">
                              <span className="font-semibold block text-rose-950">Payment Unavailable</span>
                              <p className="text-[11px] leading-relaxed text-rose-800">
                                {booking.rejection_reason ? (
                                  <>
                                    <span className="font-semibold text-rose-950">Reason: </span>
                                    <span>{booking.rejection_reason}</span>
                                  </>
                                ) : (
                                  'This booking request was rejected by the owner.'
                                )}
                              </p>
                            </div>
                          </div>
                        )}

                        {/* Payment Error Alert */}
                        {paymentError && (
                          <div className="rounded-2xl bg-rose-50 border border-rose-200 p-3 text-xs text-rose-800 flex items-start gap-2">
                            <AlertTriangle size={15} className="text-rose-600 shrink-0 mt-0.5" />
                            <div className="flex-1">
                              <span className="font-semibold block">Payment issue:</span>
                              <span>{paymentError}</span>
                            </div>
                          </div>
                        )}

                        {/* Payment Success Toast */}
                        {paymentSuccess && booking.status !== 'cancelled' && (
                          <div className="rounded-2xl bg-emerald-50 border border-emerald-200 p-3 text-xs text-emerald-800 flex items-start gap-2">
                            <CheckCircle2 size={15} className="text-emerald-600 shrink-0 mt-0.5" />
                            <div className="flex-1">
                              <span className="font-semibold block">Payment Verified!</span>
                              <span>Your payment is complete. Handover is unlocked.</span>
                            </div>
                          </div>
                        )}

                        {/* Prominent Pay Now Button for Renter (Online only) */}
                        {canShowPayNow && (
                          <div className="pt-2 space-y-2">
                            <button
                              type="button"
                              onClick={handlePayNow}
                              disabled={paying}
                              className="w-full flex items-center justify-center gap-2 rounded-2xl bg-[#D97745] py-3.5 px-4 font-bold text-white text-sm shadow-md hover:bg-[#B85D32] transition disabled:opacity-50 cursor-pointer"
                            >
                              <CreditCard size={18} />
                              {paying ? 'Connecting to Razorpay...' : `Pay ₹${booking.total_amount} Now`}
                            </button>
                            <p className="text-center text-[11px] text-gray-500">
                              🔒 100% Secure Checkout via Razorpay (UPI, Cards, NetBanking)
                            </p>
                          </div>
                        )}

                        {/* Download Invoice / Receipt button for confirmed payments */}
                        {booking.payment_status === 'paid' && booking.status !== 'cancelled' && (!isOwner || booking.renter?.id === viewerId) && (
                          <div className="pt-2 space-y-2">
                            <button
                              type="button"
                              onClick={handleDownloadInvoice}
                              disabled={downloadingInvoice}
                              className="w-full flex items-center justify-center gap-2 rounded-2xl border border-orange-200 bg-white hover:bg-orange-50 py-3 px-4 font-bold text-[#49362D] text-xs shadow-xs transition disabled:opacity-50 cursor-pointer"
                            >
                              <FileText size={16} className="text-[#D97745]" />
                              {downloadingInvoice ? 'Generating Receipt...' : 'Download Invoice / Receipt (PDF)'}
                            </button>
                            {downloadInvoiceError && (
                              <p className="text-xs text-rose-600 text-center font-medium">
                                {downloadInvoiceError}
                              </p>
                            )}
                          </div>
                        )}

                        {/* Prominent Confirm Offline Cash Button for Host/Admin */}
                        {booking.can_confirm_offline_payment && (
                          <div className="pt-2 space-y-2">
                            <button
                              type="button"
                              onClick={handleConfirmOfflinePayment}
                              disabled={confirmingOffline}
                              className="w-full flex items-center justify-center gap-2 rounded-2xl bg-emerald-600 py-3.5 px-4 font-bold text-white text-sm shadow-md hover:bg-emerald-700 transition disabled:opacity-50 cursor-pointer"
                            >
                              <Banknote size={18} />
                              {confirmingOffline ? 'Confirming...' : `Confirm Receipt of ₹${booking.total_amount} Cash`}
                            </button>
                            <p className="text-center text-[11px] text-gray-500">
                              Confirm only after receiving cash from the renter in person at pickup.
                            </p>
                          </div>
                        )}

                        {/* Pay at Pickup Notice for Renter */}
                        {booking.payment_method === 'offline' && booking.payment_status === 'pending' && booking.status === 'waiting_for_pickup' && !booking.can_confirm_offline_payment && (
                          <div className="pt-2">
                            <div className="rounded-2xl bg-amber-50/70 border border-amber-200/60 p-3 text-xs text-amber-800 flex items-start gap-2">
                              <Banknote size={16} className="text-[#D97745] shrink-0 mt-0.5" />
                              <div className="text-[11px] leading-relaxed">
                                <span className="font-semibold text-amber-950 block mb-0.5">Pay at Pickup:</span>
                                Please pay ₹{booking.total_amount} in cash directly to the host when picking up the item. The host will confirm receipt on their device.
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Prominent Pickup Handover (OTP Verification) for Host */}
                        {isOwner && booking.status === 'waiting_for_pickup' && booking.payment_status === 'paid' && (
                          <div className="pt-2 space-y-2">
                            <button
                              type="button"
                              onClick={() => setOtpModalOpen(true)}
                              className="w-full flex items-center justify-center gap-2 rounded-2xl bg-[#D97745] py-3.5 px-4 font-bold text-white text-sm shadow-md hover:bg-[#B85D32] transition cursor-pointer"
                            >
                              <ShieldCheck size={18} />
                              {booking.has_active_pickup_otp ? 'Verify Pickup OTP' : 'Confirm Pickup / Send OTP'}
                            </button>
                            <p className="text-center text-[11px] text-gray-500">
                              Sends a 6-digit OTP to renter's phone to verify item handover.
                            </p>
                          </div>
                        )}

                        {/* Waiting for Pickup Notice for Renter */}
                        {!isOwner && booking.status === 'waiting_for_pickup' && (
                          <div className="pt-2">
                            <div className="rounded-2xl bg-orange-50/80 border border-orange-200 p-3.5 text-xs text-[#352720] space-y-2">
                              <div className="flex items-center gap-2 font-bold text-[#9D4C29]">
                                <ShieldCheck size={16} />
                                <span>Waiting for Pickup Verification</span>
                              </div>
                              <p className="text-[11px] text-gray-600 leading-relaxed">
                                When you meet the host to collect <strong>{booking.item?.name}</strong>, the host will initiate pickup verification.
                                You will receive a secure 6-digit OTP via SMS on your registered mobile number ({booking.renter_phone_masked || 'registered phone'}).
                                Share this OTP with the host in person to confirm pickup.
                              </p>
                            </div>
                          </div>
                        )}

                        {/* Rental in Progress Status for both Renter and Owner */}
                        {booking.status === 'rental_in_progress' && (
                          <div className="pt-2">
                            <div className="rounded-2xl bg-emerald-50 border border-emerald-200 p-3.5 text-xs text-emerald-900 flex items-start gap-2.5">
                              <CheckCircle2 size={18} className="text-emerald-600 shrink-0 mt-0.5" />
                              <div className="flex-1 text-[11px] leading-relaxed">
                                <span className="font-bold block text-emerald-950 text-xs">Pickup Confirmed</span>
                                Handover was confirmed on <strong className="text-emerald-950">{booking.pickup_confirmed_at_display || booking.picked_up_at_display}</strong>.
                                The rental timer is actively running.
                              </div>
                            </div>
                          </div>
                        )}
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

      {/* Pickup OTP Modal */}
      <PickupOtpModal
        booking={booking}
        isOpen={otpModalOpen}
        onClose={() => setOtpModalOpen(false)}
        onSuccess={() => {
          reloadDetails()
        }}
      />
    </div>
  )
}
