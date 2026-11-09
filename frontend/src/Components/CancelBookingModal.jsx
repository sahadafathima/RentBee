import { useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'

export default function CancelBookingModal({ booking, isOpen, onClose, onConfirm, loading }) {
  const [reason, setReason] = useState('')

  if (!isOpen || !booking) return null

  const handleConfirm = () => {
    onConfirm(booking.id, reason)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 backdrop-blur-xs">
      <div className="relative w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl border border-orange-100 animate-in fade-in zoom-in-95 duration-200">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 rounded-full p-1.5 text-gray-400 hover:bg-orange-50 hover:text-[#D97745] transition"
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

        <div className="mt-4 rounded-2xl bg-[#FFF9F5] border border-orange-100 p-3.5 text-xs text-[#49362D]">
          <p className="font-semibold text-[#352720]">{booking.item?.name}</p>
          <p className="mt-1 text-gray-600">
            Rental dates: {booking.start_date} to {booking.end_date} ({booking.duration_days} {booking.duration_days === 1 ? 'day' : 'days'})
          </p>
        </div>

        <p className="mt-3 text-xs text-gray-600 leading-relaxed">
          Are you sure you want to cancel this booking? This will release your reserved rental dates.
          You can only cancel before pickup confirmation.
        </p>

        <div className="mt-4">
          <label className="block text-xs font-semibold text-[#352720] mb-1">
            Reason for cancellation (optional):
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Schedule changed, booked another item..."
            rows={2}
            className="w-full rounded-xl border border-orange-200 bg-white p-2.5 text-xs text-[#352720] placeholder-gray-400 focus:border-[#D97745] focus:outline-none focus:ring-2 focus:ring-orange-200/50"
          />
        </div>

        <div className="mt-6 flex flex-wrap justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="rounded-xl border border-orange-200 bg-white px-4 py-2 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition"
          >
            Keep Booking
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700 transition disabled:opacity-50"
          >
            {loading ? 'Cancelling...' : 'Yes, Cancel Booking'}
          </button>
        </div>
      </div>
    </div>
  )
}

