import { useLocation, useNavigate } from 'react-router-dom'
import { CheckCircle2, ArrowRight, Home, Calendar, ShieldCheck, Tag } from 'lucide-react'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'

function BookingSuccess() {
  const location = useLocation()
  const navigate = useNavigate()
  const booking = location.state?.booking

  return (
    <div className="flex min-h-screen flex-col bg-[#FFFCF9]">
      <Navbar />

      <main className="flex-1 py-10 px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl">
          {/* Main Success Card */}
          <div className="rounded-3xl border border-[#F0E4DE] bg-white p-6 sm:p-10 shadow-sm text-center">
            {/* Green Tick Icon */}
            <div className="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 shadow-inner">
              <CheckCircle2 size={48} className="stroke-[2.2]" />
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold text-[#352720]">
              Booking Request Submitted!
            </h1>

            <p className="mt-2 text-base text-[#6E584E]">
              Your booking request has been sent to the item owner for approval.
            </p>

            {/* Owner Approval Notice */}
            <div className="mt-6 rounded-2xl border border-amber-100 bg-[#FFF9F5] p-4 text-left sm:p-5">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#D97745]/15 text-[#D97745] font-bold text-xs">
                  ℹ
                </span>
                <div className="text-xs sm:text-sm text-[#735548] leading-relaxed">
                  <p className="font-semibold text-[#352720] mb-0.5">What happens next?</p>
                  The owner has 24 hours to review and approve your request. Once approved, your booking status will change to <strong className="text-[#352720]">Waiting for Pickup</strong> and the owner&apos;s full pickup address and contact info will be revealed.
                </div>
              </div>
            </div>

            {/* Booking Details Card */}
            {booking ? (
              <div className="mt-6 rounded-2xl border border-[#F0E4DE] bg-[#FAF6F3] p-5 text-left">
                {/* Item Summary */}
                <div className="flex items-center gap-4 pb-4 border-b border-[#EBDDD4]">
                  {booking.item?.primary_image_url ? (
                    <img
                      src={booking.item.primary_image_url}
                      alt={booking.item.name}
                      className="h-20 w-20 rounded-xl object-cover border border-[#E8D9D0]"
                    />
                  ) : (
                    <div className="flex h-20 w-20 items-center justify-center rounded-xl bg-[#EFE6E0] text-2xl">
                      📦
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <span className="inline-block rounded-md bg-[#FFF0E7] px-2 py-0.5 text-xs font-semibold text-[#D97745]">
                      {booking.item?.category_name || 'Rental Item'}
                    </span>
                    <h3 className="mt-1 font-bold text-[#352720] text-base truncate">
                      {booking.item?.name}
                    </h3>
                    <p className="text-xs font-mono text-[#8B776D] mt-0.5">
                      Booking Ref: <span className="font-semibold text-[#352720]">{booking.booking_reference || `#BK-${booking.id}`}</span>
                    </p>
                  </div>
                </div>

                {/* Rental Specs */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4 border-b border-[#EBDDD4] text-xs sm:text-sm">
                  <div className="flex items-start gap-2.5">
                    <Calendar size={18} className="text-[#D97745] shrink-0 mt-0.5" />
                    <div>
                      <span className="text-[#8B776D] block">Rental Period:</span>
                      <span className="font-semibold text-[#352720]">
                        {booking.start_date} → {booking.end_date}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5">
                    <Tag size={18} className="text-[#D97745] shrink-0 mt-0.5" />
                    <div>
                      <span className="text-[#8B776D] block">Requested Quantity:</span>
                      <span className="font-semibold text-[#352720]">{booking.requested_quantity || 1} unit{(booking.requested_quantity || 1) === 1 ? '' : 's'}</span>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5">
                    <Tag size={18} className="text-[#D97745] shrink-0 mt-0.5" />
                    <div>
                      <span className="text-[#8B776D] block">Duration:</span>
                      <span className="font-semibold text-[#352720]">
                        {booking.duration_days} day{booking.duration_days > 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Price Breakdown */}
                <div className="pt-4 space-y-2 text-xs sm:text-sm">
                  <div className="flex justify-between text-[#6E584E]">
                    <span>Rental Rate ({booking.requested_quantity || 1} × {booking.duration_days}d × ₹{Number(booking.daily_price || 0).toLocaleString()}):</span>
                    <span className="font-semibold text-[#352720]">₹{Number(booking.rental_amount || 0).toLocaleString()}</span>
                  </div>

                  <div className="flex justify-between text-[#6E584E]">
                    <span className="inline-flex items-center gap-1">
                      <ShieldCheck size={14} className="text-emerald-600" /> Refundable Security Deposit:
                    </span>
                    <span className="font-semibold text-[#352720]">₹{Number(booking.deposit_amount || 0).toLocaleString()}</span>
                  </div>

                  <div className="flex justify-between pt-2 border-t border-[#EBDDD4] text-sm sm:text-base font-bold text-[#352720]">
                    <span>Total Amount:</span>
                    <span className="text-[#D97745]">₹{Number(booking.total_amount || 0).toLocaleString()}</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-6 rounded-2xl border border-dashed border-[#EBDDD4] p-6 text-sm text-[#8B776D]">
                Your booking request has been recorded in the platform database.
              </div>
            )}

            {/* Exactly Two Action Buttons */}
            <div className="mt-8 flex flex-col-reverse sm:flex-row gap-3 justify-center">
              <button
                type="button"
                onClick={() => navigate('/')}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#E8D9D0] bg-white px-6 py-3 text-sm font-semibold text-[#49362D] hover:bg-[#FFF9F5] transition"
              >
                <Home size={17} /> Back to Home
              </button>

              <button
                type="button"
                onClick={() => navigate('/bookings')}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#D97745] px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-[#B85D32] transition"
              >
                View My Bookings <ArrowRight size={17} />
              </button>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  )
}

export default BookingSuccess
