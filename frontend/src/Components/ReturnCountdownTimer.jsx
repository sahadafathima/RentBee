import { useEffect, useState } from 'react'
import { Clock, Hourglass, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { formatKolkataDateTime, calculateReturnCountdown } from '../utils/dateUtils'

/**
 * Shared Return Countdown Timer Component
 * Reused on both Owner and User sides with zero duplicate logic.
 *
 * Props:
 * - booking: booking data object
 * - compact: boolean, renders a compact card (for lists / dashboards) or full card
 */
export default function ReturnCountdownTimer({ booking, compact = false }) {
  const [, setTick] = useState(0)

  useEffect(() => {
    if (!booking?.return_deadline || booking.status !== 'rental_in_progress') {
      return
    }

    const timer = setInterval(() => {
      setTick((t) => t + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [booking?.return_deadline, booking?.status])

  if (!booking) return null

  const countdown = calculateReturnCountdown(booking.return_deadline)

  // Compact layout (used inside HostHub or booking lists)
  if (compact) {
    if (booking.status !== 'rental_in_progress' || !booking.return_deadline) {
      return null
    }

    return (
      <div className="mt-2 rounded-xl bg-[#FFF9F5] border border-orange-200/80 p-2.5 text-xs text-[#352720] space-y-1">
        <div className="flex items-center gap-1.5 font-bold text-[#9D4C29]">
          <Clock size={13} />
          <span>Return Deadline: {booking.return_deadline_display || formatKolkataDateTime(booking.return_deadline)}</span>
        </div>
        <div className="text-[11px] text-gray-500 flex flex-wrap items-center justify-between gap-1">
          <span>Picked up: {booking.picked_up_at_display || formatKolkataDateTime(booking.picked_up_at)}</span>
          <span className={`font-semibold ${countdown.isOverdue ? 'text-rose-600' : 'text-emerald-700'}`}>
            {countdown.isOverdue ? `Rental Period Expired (${countdown.text})` : countdown.text}
          </span>
        </div>
        {!countdown.isOverdue && countdown.isValid && (
          <div className="text-[11px] font-bold text-emerald-800 flex items-center justify-between gap-1 pt-1 border-t border-orange-100/60">
            <span className="flex items-center gap-1">
              <Hourglass size={12} className="text-emerald-600 animate-pulse" />
              Rental Time Remaining:
            </span>
            <span className="font-mono">
              {countdown.days > 0 ? `${countdown.days}d ` : ''}
              {countdown.hours}h {countdown.minutes}m {countdown.seconds}s
            </span>
          </div>
        )}
      </div>
    )
  }

  // Full detailed schedule & live countdown layout (used on Rental / Booking Details)
  return (
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

            {/* Live Countdown / Expired Alert */}
            {countdown.isOverdue ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50/70 p-4 text-xs text-rose-950 flex items-start gap-3">
                <AlertTriangle size={18} className="text-rose-600 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-bold text-sm text-rose-900">
                      Rental Period Expired
                    </h3>
                    <span className="rounded-full bg-rose-100 border border-rose-200 px-2.5 py-0.5 text-[11px] font-bold text-rose-800">
                      Return Deadline Has Passed
                    </span>
                  </div>
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
                  <div className="text-base sm:text-lg font-black text-emerald-800 font-mono">
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
            <span>Booking Request Rejected</span>
          </div>
          <p className="leading-relaxed text-gray-600">
            This booking request was rejected by the owner and did not proceed to rental.
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
  )
}

