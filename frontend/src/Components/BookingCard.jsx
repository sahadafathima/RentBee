import { Link } from 'react-router-dom'
import { Calendar, ShieldCheck, UserCheck, AlertCircle, Clock, Package, Tag } from 'lucide-react'
import ReturnCountdownTimer from './ReturnCountdownTimer'

export default function BookingCard({ booking, onCancelClick }) {
  if (!booking) return null

  const {
    id,
    booking_reference,
    status,
    start_date,
    end_date,
    duration_days,
    requested_quantity,
    rental_amount,
    discount_amount,
    deposit_amount,
    total_amount,
    payment_method,
    payment_method_display,
    item,
    owner,
    rejection_reason,
    cancellation_reason,
  } = booking

  // Status badge config
  const getStatusBadge = () => {
    switch (status) {
      case 'pending_approval':
        return {
          label: 'Waiting for Owner Approval',
          className: 'bg-amber-50 text-amber-800 border-amber-200',
          dot: 'bg-amber-500',
        }
      case 'waiting_for_pickup':
        return {
          label: 'Waiting for Pickup',
          className: 'bg-orange-50 text-[#9D4C29] border-orange-200',
          dot: 'bg-[#D97745]',
        }
      case 'rental_in_progress':
        return {
          label: 'Rental in Progress',
          className: 'bg-blue-50 text-blue-800 border-blue-200',
          dot: 'bg-blue-600',
        }
      case 'completed':
        return {
          label: 'Completed',
          className: 'bg-emerald-50 text-emerald-800 border-emerald-200',
          dot: 'bg-emerald-600',
        }
      case 'rejected':
        return {
          label: 'Declined by Owner',
          className: 'bg-gray-100 text-gray-700 border-gray-300',
          dot: 'bg-gray-500',
        }
      case 'expired':
        return {
          label: 'Request Expired',
          className: 'bg-slate-100 text-slate-700 border-slate-300',
          dot: 'bg-slate-500',
        }
      case 'cancelled':
      default:
        if (booking.payment_status === 'refunded' || booking.refund_status === 'processed') {
          return {
            label: booking.payment_method === 'offline' ? 'Cancelled & Cash Returned' : 'Cancelled & Refunded',
            className: 'bg-purple-50 text-purple-800 border-purple-200',
            dot: 'bg-purple-600',
          }
        }
        if (booking.refund_status === 'pending' || (booking.payment_method === 'offline' && booking.payment_status === 'paid')) {
          return {
            label: booking.payment_method === 'offline' ? 'Cancelled (Cash Return Pending)' : 'Cancelled (Refund Processing)',
            className: 'bg-amber-50 text-amber-800 border-amber-200',
            dot: 'bg-amber-500',
          }
        }
        if (booking.refund_status === 'failed') {
          return {
            label: 'Cancelled (Refund Failed)',
            className: 'bg-rose-100 text-rose-900 border-rose-300',
            dot: 'bg-rose-600',
          }
        }
        return {
          label: 'Cancelled by You',
          className: 'bg-rose-50 text-rose-800 border-rose-200',
          dot: 'bg-rose-500',
        }
    }
  }

  const badge = getStatusBadge()

  return (
    <div className="rounded-3xl border border-orange-100 bg-white p-5 sm:p-6 shadow-xs transition hover:shadow-md">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">

        {/* Left: Item Image & Primary Details */}
        <div className="flex flex-1 flex-col gap-4 sm:flex-row sm:items-center">
          {/* Image */}
          <div className="relative h-28 w-28 shrink-0 overflow-hidden rounded-2xl bg-orange-50 border border-orange-100 self-center sm:self-start">
            {item?.primary_image_url ? (
              <img
                src={item.primary_image_url}
                alt={item.name}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-orange-300">
                <Package size={36} />
              </div>
            )}
          </div>

          {/* Details */}
          <div className="flex-1 min-w-0">
            {/* Top row: Category & Booking Reference */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-semibold uppercase tracking-wider text-[#D97745]">
                {item?.category_name || 'Rental Item'}
              </span>
              <span className="text-gray-300">•</span>
              <span className="font-mono font-medium text-gray-500">
                {booking_reference}
              </span>
              <span className="rounded bg-orange-50 border border-orange-200 px-2 py-0.5 text-[10px] font-semibold text-[#9D4C29]">
                {payment_method_display || (payment_method === 'offline' ? 'Pay at Pickup' : 'Online')}
              </span>
            </div>

            {/* Item Name */}
            <h3 className="mt-1 text-base sm:text-lg font-bold text-[#352720] truncate">
              {item?.name}
            </h3>

            {/* Owner Info */}
            <div className="mt-1 flex items-center gap-1.5 text-xs text-gray-500">
              <span>Owner:</span>
              <span className="font-semibold text-[#49362D]">{owner?.full_name}</span>
              {owner?.is_verified && (
                <span
                  title="Verified Lender"
                  className="inline-flex items-center text-[#D97745]"
                >
                  <UserCheck size={13} />
                </span>
              )}
            </div>

            {/* Schedule & Duration */}
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-600">
              <div className="flex items-center gap-1.5">
                <Calendar size={14} className="text-[#D97745]" />
                <span>
                  {start_date} → {end_date}
                </span>
              </div>
              <div className="flex items-center gap-1.5 font-medium text-[#9D4C29]">
                <Clock size={14} />
                <span>{duration_days} {duration_days === 1 ? 'day' : 'days'}</span>
              </div>
              <div className="flex items-center gap-1.5 font-medium text-[#49362D]">
                <Package size={14} className="text-[#D97745]" />
                <span>{requested_quantity || 1} unit{(requested_quantity || 1) === 1 ? '' : 's'}</span>
              </div>
            </div>

            {/* In-progress Return Deadline & Countdown */}
            <ReturnCountdownTimer booking={booking} compact={true} />
          </div>
        </div>

        {/* Right / Pricing & Status Badge */}
        <div className="flex flex-row justify-between items-end sm:flex-col sm:items-end sm:justify-start gap-2 border-t border-orange-50 pt-3 sm:border-0 sm:pt-0">
          <div className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold shadow-2xs">
            <span className={`h-2 w-2 rounded-full ${badge.dot}`} />
            <span className={badge.className.split(' ')[1]}>{badge.label}</span>
          </div>

          <div className="text-right">
            <span className="text-xs text-gray-400">Total Rental</span>
            <div className="text-lg sm:text-xl font-black text-[#9D4C29]">
              ₹{total_amount}
            </div>
            {parseFloat(discount_amount || 0) > 0 && (
              <div className="mt-0.5">
                <span className="inline-flex items-center gap-1 rounded bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
                  <Tag size={10} className="text-emerald-600" /> 10% First Booking Off
                </span>
              </div>
            )}
            <div className="text-[11px] text-gray-500">
              (Rental: ₹{rental_amount} + Deposit: ₹{deposit_amount})
            </div>
          </div>
        </div>

      </div>

      {/* Waiting for Pickup OTP Notice for Renter */}
      {status === 'waiting_for_pickup' && (
        <div className="mt-3 rounded-xl bg-orange-50/70 border border-orange-200/60 p-2.5 text-xs text-[#352720] flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-[11px] text-[#9D4C29]">
            <ShieldCheck size={14} className="text-[#D97745] shrink-0" />
            <span>Pickup OTP will be sent to your mobile ({booking.renter_phone_masked || 'via SMS'}) when the host initiates handover.</span>
          </div>
        </div>
      )}

      {/* Rejection / Cancellation note if present */}
      {(rejection_reason || cancellation_reason) && (
        <div className="mt-4 rounded-xl bg-orange-50/60 border border-orange-100 p-2.5 text-xs text-gray-600 flex items-start gap-2">
          <AlertCircle size={14} className="text-[#D97745] shrink-0 mt-0.5" />
          <div>
            <strong className="text-[#352720]">
              {rejection_reason ? 'Decline Reason:' : 'Cancellation Reason:'}
            </strong>{' '}
            {rejection_reason || cancellation_reason}
          </div>
        </div>
      )}

      {/* Refund status indicator on card when cancelled */}
      {status === 'cancelled' && (booking.payment_method === 'online' || booking.payment_status === 'paid' || booking.refund_status) && (
        <div className="mt-3">
          {(booking.payment_status === 'refunded' || booking.refund_status === 'processed') ? (
            <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-2.5 text-xs text-emerald-900 flex items-center justify-between">
              <span className="font-semibold">
                ✓ 100% Refunded (₹{booking.refund_amount || total_amount})
              </span>
              {booking.refund_transaction_id && (
                <span className="text-[10px] text-emerald-700 font-mono">
                  Ref: {booking.refund_transaction_id}
                </span>
              )}
            </div>
          ) : booking.refund_status === 'failed' ? (
            <div className="rounded-xl bg-rose-50 border border-rose-200 p-2.5 text-xs text-rose-900 flex items-center justify-between">
              <span className="font-semibold">
                ⚠ Refund Failed (₹{booking.refund_amount || total_amount})
              </span>
              <span className="text-[10px] text-rose-700">See details to retry</span>
            </div>
          ) : (booking.refund_status === 'pending' || (booking.payment_method === 'offline' && booking.payment_status === 'paid')) ? (
            <div className="rounded-xl bg-amber-50 border border-amber-200 p-2.5 text-xs text-amber-900 flex items-center justify-between">
              <span className="font-semibold">
                ⏳ {booking.payment_method === 'offline' ? 'Cash Return Pending' : 'Refund Processing'} (₹{booking.refund_amount || total_amount})
              </span>
              <span className="text-[10px] text-amber-700">
                {booking.payment_method === 'offline' ? 'Host return pending' : 'Razorpay clearance pending'}
              </span>
            </div>
          ) : null}
        </div>
      )}

      {/* Bottom Section: Dynamic Action Buttons */}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-orange-100/80 pt-4">

        {/* Helper info or reassurance */}
        <div className="text-xs text-gray-400 flex items-center gap-1.5">
          <ShieldCheck size={14} className="text-emerald-600" />
          <span>RentBee Secure Handover Protection</span>
        </div>

        {/* Dynamic Buttons per Status */}
        <div className="flex flex-wrap items-center gap-2">

          {/* Waiting for Owner Approval: [View Details] [Cancel Request] */}
          {status === 'pending_approval' && (
            <>
              <Link
                to={`/bookings/${id}`}
                className="rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition"
              >
                View Details
              </Link>
              <button
                type="button"
                onClick={() => onCancelClick(booking)}
                className="rounded-xl border border-rose-200 bg-white px-4 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 transition cursor-pointer"
              >
                Cancel Request
              </button>
            </>
          )}

          {/* Waiting for Pickup: [View Details] [Cancel Booking] */}
          {status === 'waiting_for_pickup' && (
            <>
              <Link
                to={`/bookings/${id}`}
                className="rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition"
              >
                View Details
              </Link>
              <button
                type="button"
                onClick={() => onCancelClick(booking)}
                className="rounded-xl border border-rose-200 bg-white px-4 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 transition cursor-pointer"
              >
                Cancel Booking
              </button>
            </>
          )}


          {/* Rental in Progress: [View Details] [Report Any Problem] */}
          {status === 'rental_in_progress' && (
            <>
              <Link
                to={`/bookings/${id}`}
                className="rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition"
              >
                View Details
              </Link>
              <Link
                to={`/report-problem/${id}`}
                className="rounded-xl bg-[#D97745] px-4 py-2 text-xs font-semibold text-white hover:bg-[#B85D32] transition"
              >
                Report Any Problem
              </Link>
            </>
          )}

          {/* Completed: [View Details] [Book Again] */}
          {status === 'completed' && (
            <>
              <Link
                to={`/bookings/${id}`}
                className="rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition"
              >
                View Details
              </Link>
              <Link
                to={`/request-booking/${item?.id}`}
                className="rounded-xl bg-[#9D4C29] px-4 py-2 text-xs font-semibold text-white hover:bg-[#813B20] transition"
              >
                Book Again
              </Link>
            </>
          )}

          {/* Cancelled / Rejected / Expired: [View Details] [Browse Items] */}
          {['cancelled', 'rejected', 'expired'].includes(status) && (
            <>
              <Link
                to={`/bookings/${id}`}
                className="rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition"
              >
                View Details
              </Link>
              <Link
                to="/browse"
                className="rounded-xl bg-[#D97745] px-4 py-2 text-xs font-semibold text-white hover:bg-[#B85D32] transition"
              >
                Browse Items
              </Link>
            </>
          )}

        </div>
      </div>
    </div>
  )
}

