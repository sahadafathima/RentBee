import { useState } from 'react'
import { AlertTriangle, X, ShieldCheck, Banknote, CheckCircle2 } from 'lucide-react'

export default function CancelBookingModal({ booking, isOpen, onClose, onConfirm, loading }) {
  const [reason, setReason] = useState('')

  if (!isOpen || !booking) return null

  const isOnlinePaid = booking.payment_method === 'online' && booking.payment_status === 'paid'
  const isOfflinePaid = booking.payment_method === 'offline' && booking.payment_status === 'paid'
  const isUnpaid = booking.payment_status !== 'paid'

  const handleConfirm = () => {
    onConfirm(booking.id, reason)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-xs overflow-y-auto py-6">
      <div className="relative w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl border border-orange-100 animate-in fade-in zoom-in-95 duration-200">
        <button
          type="button"
          onClick={onClose}
          disabled={loading}
          className="absolute right-4 top-4 rounded-full p-1.5 text-gray-400 hover:bg-orange-50 hover:text-[#D97745] transition disabled:opacity-50"
        >
          <X size={18} />
        </button>

        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
            <AlertTriangle size={22} />
          </div>
          <div>
            <h3 className="text-base font-bold text-[#352720]">Cancel Booking Request</h3>
            <p className="text-xs text-gray-500 font-mono">{booking.booking_reference}</p>
          </div>
        </div>

        {/* Item summary */}
        <div className="mt-4 rounded-2xl bg-[#FFF9F5] border border-orange-100 p-3.5 text-xs text-[#49362D]">
          <p className="font-semibold text-[#352720]">{booking.item?.name}</p>
          <p className="mt-1 text-gray-600">
            Rental dates: {booking.start_date} to {booking.end_date} ({booking.duration_days} {booking.duration_days === 1 ? 'day' : 'days'})
          </p>
        </div>

        {/* Scenario C: Online Paid Booking -> 100% Refund Policy */}
        {isOnlinePaid && (
          <div className="mt-4 rounded-2xl bg-emerald-50/80 border border-emerald-200 p-4 text-xs text-emerald-950 space-y-3">
            <div className="flex items-center gap-2 text-emerald-800 font-bold">
              <ShieldCheck size={18} className="text-emerald-600 shrink-0" />
              <span>100% Refund Guaranteed</span>
            </div>

            <p className="text-emerald-900 leading-relaxed text-[11px]">
              You have paid <span className="font-bold">₹{booking.total_amount}</span>. If you cancel before pickup, 100% of the paid amount will be refunded to your original payment method. No cancellation fee will be charged.
            </p>

            <div className="rounded-xl bg-white/90 border border-emerald-100 p-3 space-y-1.5 text-[11px]">
              <div className="flex justify-between text-gray-600">
                <span>Total Amount Paid:</span>
                <span className="font-semibold text-gray-900">₹{booking.total_amount}</span>
              </div>
              <div className="flex justify-between text-gray-600">
                <span>Rental Amount:</span>
                <span className="font-semibold text-gray-900">₹{booking.rental_amount}</span>
              </div>
              <div className="flex justify-between text-gray-600">
                <span>Security Deposit:</span>
                <span className="font-semibold text-gray-900">₹{booking.deposit_amount}</span>
              </div>
              <div className="flex justify-between text-emerald-700">
                <span>Cancellation Fee:</span>
                <span className="font-bold">₹0 (Free Cancellation)</span>
              </div>
              <div className="flex justify-between text-emerald-700">
                <span>Refund Policy:</span>
                <span className="font-bold">100% Full Refund</span>
              </div>
              <div className="flex justify-between text-gray-600">
                <span>Refund Destination:</span>
                <span className="font-semibold text-gray-900">Original Payment Method (Razorpay)</span>
              </div>
              <div className="pt-2 border-t border-emerald-100 flex justify-between font-bold text-emerald-900 text-xs">
                <span>Total Refund Amount:</span>
                <span>₹{booking.total_amount}</span>
              </div>
            </div>

            <p className="text-[10px] text-emerald-700">
              ⚡ Razorpay initiates the refund immediately. Final processing by your issuing bank typically takes 5–7 business days.
            </p>
          </div>
        )}

        {/* Scenario: Offline Cash Paid Booking -> Manual Cash Return Notice */}
        {isOfflinePaid && (
          <div className="mt-4 rounded-2xl bg-amber-50/80 border border-amber-200 p-4 text-xs text-amber-950 space-y-3">
            <div className="flex items-center gap-2 text-amber-900 font-bold">
              <Banknote size={18} className="text-[#D97745] shrink-0" />
              <span>Manual Cash Return Required</span>
            </div>

            <p className="text-amber-900 leading-relaxed text-[11px]">
              You have paid <span className="font-bold">₹{booking.total_amount}</span> in cash to the host. Since you are cancelling before pickup, the host will return 100% of this amount directly to you in cash.
            </p>

            <div className="rounded-xl bg-white/90 border border-amber-100 p-3 space-y-1.5 text-[11px]">
              <div className="flex justify-between text-gray-600">
                <span>Cash Paid at Pickup:</span>
                <span className="font-semibold text-gray-900">₹{booking.total_amount}</span>
              </div>
              <div className="flex justify-between text-gray-600">
                <span>Rental Amount:</span>
                <span className="font-semibold text-gray-900">₹{booking.rental_amount}</span>
              </div>
              <div className="flex justify-between text-gray-600">
                <span>Security Deposit:</span>
                <span className="font-semibold text-gray-900">₹{booking.deposit_amount}</span>
              </div>
              <div className="flex justify-between text-amber-700">
                <span>Cancellation Fee:</span>
                <span className="font-bold">₹0</span>
              </div>
              <div className="pt-2 border-t border-amber-100 flex justify-between font-bold text-amber-900 text-xs">
                <span>Total Cash Refund:</span>
                <span>₹{booking.total_amount}</span>
              </div>
            </div>

            <p className="text-[10px] text-amber-800">
              Please coordinate directly with the host to collect your full cash refund.
            </p>
          </div>
        )}

        {/* Scenario A & B: Unpaid Booking */}
        {isUnpaid && (
          <p className="mt-3 text-xs text-gray-600 leading-relaxed">
            Are you sure you want to cancel this booking? This will release your reserved rental dates. No payment was collected, so no refund is required.
          </p>
        )}

        <div className="mt-4">
          <label className="block text-xs font-semibold text-[#352720] mb-1">
            Reason for cancellation (optional):
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={loading}
            placeholder="e.g. Schedule changed, booked another item..."
            rows={2}
            className="w-full rounded-xl border border-orange-200 bg-white p-2.5 text-xs text-[#352720] placeholder-gray-400 focus:border-[#D97745] focus:outline-none focus:ring-2 focus:ring-orange-200/50 disabled:bg-gray-50"
          />
        </div>

        <div className="mt-6 flex flex-wrap justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition disabled:opacity-50 cursor-pointer"
          >
            Keep Booking
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700 transition disabled:opacity-50 cursor-pointer shadow-xs"
          >
            {loading ? (
              <>
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-solid border-white border-r-transparent" />
                <span>Cancelling...</span>
              </>
            ) : isOnlinePaid ? (
              'Yes, Cancel & Refund 100%'
            ) : (
              'Yes, Cancel Booking'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
