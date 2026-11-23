import { useLocation, useNavigate } from 'react-router-dom'
import { CheckCircle2, ArrowRight, Home, Calendar, ShieldCheck, Tag, MapPin, CreditCard, Banknote } from 'lucide-react'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'

function BookingSuccess() {
  const location = useLocation()
  const navigate = useNavigate()
  const booking = location.state?.booking
  const renterAddress = booking?.renter_address || booking?.renter?.address_info

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

                  {/* Payment Method */}
                  <div className="flex items-start gap-2.5">
                    {booking.payment_method === 'offline' ? (
                      <Banknote size={18} className="text-[#D97745] shrink-0 mt-0.5" />
                    ) : (
                      <CreditCard size={18} className="text-[#D97745] shrink-0 mt-0.5" />
                    )}
                    <div>
                      <span className="text-[#8B776D] block">Payment Method:</span>
                      <span className="font-semibold text-[#352720]">
                        {booking.payment_method_display ||
                          (booking.payment_method === 'offline'
                            ? 'Pay at Pickup (Cash)'
                            : 'Online Payment (Razorpay)')}
                      </span>
                    </div>
                  </div>

                  {/* Payment Status */}
                  <div className="flex items-start gap-2.5">
                    <ShieldCheck size={18} className="text-emerald-600 shrink-0 mt-0.5" />
                    <div>
                      <span className="text-[#8B776D] block">Payment Status:</span>
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-bold ${
                          booking.payment_status === 'paid'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {booking.payment_status_display ||
                          (booking.payment_status === 'paid' ? 'Payment Verified' : 'Pending Payment')}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Delivery / Contact Address */}
                {renterAddress && (renterAddress.full_formatted_address || renterAddress.city) && (
                  <div className="py-4 border-b border-[#EBDDD4] text-xs sm:text-sm">
                    <div className="flex items-start gap-2.5">
                      <MapPin size={18} className="text-[#D97745] shrink-0 mt-0.5" />
                      <div>
                        <span className="text-[#8B776D] block">Delivery / Contact Address:</span>
                        <span className="font-semibold text-[#352720]">
                          {renterAddress.full_name && `${renterAddress.full_name} • `}
                          {renterAddress.full_formatted_address ||
                            [renterAddress.house_number, renterAddress.address, renterAddress.area, renterAddress.city, renterAddress.state, renterAddress.pincode].filter(Boolean).join(', ')}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Price Breakdown */}
                <div className="pt-4 space-y-2 text-xs sm:text-sm">
                  {parseFloat(booking.discount_amount || 0) > 0 && (
                    <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-2.5 text-xs text-emerald-800 flex items-center justify-between mb-2">
                      <span className="font-bold flex items-center gap-1.5">
                        <Tag size={13} className="text-emerald-600" /> First Booking 10% Discount Applied!
                      </span>
                      <span className="rounded-full bg-emerald-600 text-white font-extrabold text-[10px] px-2 py-0.5">
                        10% OFF
                      </span>
                    </div>
                  )}

                  <div className="flex justify-between text-[#6E584E]">
                    <span>
                      {parseFloat(booking.discount_amount || 0) > 0 ? 'Original Rental Rate' : 'Rental Rate'} ({booking.requested_quantity || 1} × {booking.duration_days}d × ₹{Number(booking.daily_price || 0).toLocaleString()}):
                    </span>
                    <span className={`font-semibold ${parseFloat(booking.discount_amount || 0) > 0 ? 'line-through text-gray-400' : 'text-[#352720]'}`}>
                      ₹{Number(booking.original_rental_amount || (parseFloat(booking.rental_amount || 0) + parseFloat(booking.discount_amount || 0))).toLocaleString()}
                    </span>
                  </div>

                  {parseFloat(booking.discount_amount || 0) > 0 && (
                    <div className="flex justify-between text-emerald-700 font-medium">
                      <span className="inline-flex items-center gap-1">
                        <Tag size={13} className="text-emerald-600" /> First Booking Discount (10%):
                      </span>
                      <span className="font-bold text-emerald-700">-₹{Number(booking.discount_amount).toLocaleString()}</span>
                    </div>
                  )}

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
