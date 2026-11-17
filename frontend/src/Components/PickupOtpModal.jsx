import { useState, useEffect } from 'react'
import {
  ShieldCheck,
  Smartphone,
  KeyRound,
  CheckCircle2,
  AlertCircle,
  Clock,
  X,
  RefreshCw,
  Send,
} from 'lucide-react'
import { sendPickupOtp, verifyPickupOtp } from '../services/api'

export default function PickupOtpModal({ booking, isOpen, onClose, onSuccess }) {
  const [otpSent, setOtpSent] = useState(false)
  const [maskedPhone, setMaskedPhone] = useState('')
  const [otpInput, setOtpInput] = useState('')
  const [loadingSend, setLoadingSend] = useState(false)
  const [loadingVerify, setLoadingVerify] = useState(false)
  const [error, setError] = useState('')
  const [attemptsRemaining, setAttemptsRemaining] = useState(null)
  const [cooldown, setCooldown] = useState(0)
  const [confirmed, setConfirmed] = useState(false)
  const [confirmedAt, setConfirmedAt] = useState('')

  // Reset state when booking or modal opens
  useEffect(() => {
    if (isOpen && booking) {
      setOtpInput('')
      setError('')
      setAttemptsRemaining(null)
      setConfirmed(false)
      setConfirmedAt('')

      // If backend reports an active OTP already generated, initialize state
      if (booking.has_active_pickup_otp) {
        setOtpSent(true)
        setMaskedPhone(booking.renter_phone_masked || 'renter registered mobile')
        setCooldown(booking.pickup_otp_resend_cooldown_seconds || 0)
      } else {
        setOtpSent(false)
        setMaskedPhone(booking.renter_phone_masked || '')
        setCooldown(0)
      }
    }
  }, [isOpen, booking])

  // Cooldown countdown timer
  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setInterval(() => {
      setCooldown((prev) => {
        if (prev <= 1) {
          clearInterval(timer)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [cooldown])

  if (!isOpen || !booking) return null

  // 1. Send OTP via SMS
  const handleSendOtp = async () => {
    setError('')
    setAttemptsRemaining(null)
    setLoadingSend(true)
    try {
      const res = await sendPickupOtp(booking.id)
      setOtpSent(true)
      setMaskedPhone(res.masked_phone || booking.renter_phone_masked || 'renter mobile')
      setCooldown(res.resend_cooldown_seconds || 60)
    } catch (err) {
      setError(err.message || 'Failed to dispatch pickup OTP. Please check SMS configuration.')
    } finally {
      setLoadingSend(false)
    }
  }

  // 2. Verify OTP and Confirm Pickup
  const handleVerifyOtp = async (e) => {
    if (e) e.preventDefault()
    const cleanOtp = otpInput.trim()
    if (cleanOtp.length !== 6 || !/^\d+$/.test(cleanOtp)) {
      setError('Please enter a valid 6-digit numeric OTP.')
      return
    }

    setError('')
    setLoadingVerify(true)
    try {
      const res = await verifyPickupOtp(booking.id, cleanOtp)
      setConfirmed(true)
      setConfirmedAt(res.pickup_confirmed_at || 'Just now')
      window.dispatchEvent(new Event('rentbee:bookings-changed'))

      if (onSuccess) {
        onSuccess(res)
      }

      // Auto-close after brief success display
      setTimeout(() => {
        onClose()
      }, 1800)
    } catch (err) {
      const errMsg = err.message || 'Invalid OTP. Please verify and try again.'
      setError(errMsg)
      if (err.data?.attempts_remaining !== undefined) {
        setAttemptsRemaining(err.data.attempts_remaining)
      } else if (errMsg.includes('attempt(s) remaining')) {
        const match = errMsg.match(/(\d+)\s+attempt/i)
        if (match) setAttemptsRemaining(parseInt(match[1], 10))
      }
    } finally {
      setLoadingVerify(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-xs">
      <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl border border-orange-100 relative animate-in fade-in zoom-in-95 duration-150">
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          disabled={loadingVerify || loadingSend}
          className="absolute right-4 top-4 rounded-full p-1 text-gray-400 hover:bg-orange-50 hover:text-gray-600 transition"
        >
          <X size={18} />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-2.5 pb-3 border-b border-orange-50">
          <div className="rounded-xl bg-orange-100/80 p-2 text-[#D97745]">
            <ShieldCheck size={22} />
          </div>
          <div>
            <h3 className="text-base font-bold text-[#352720]">
              Pickup OTP Verification
            </h3>
            <p className="text-[11px] text-gray-500">
              Secure Zomato-style handover confirmation
            </p>
          </div>
        </div>

        {/* Booking Summary Box */}
        <div className="mt-4 rounded-2xl bg-[#FFF9F5] border border-orange-200/60 p-3 text-xs space-y-1">
          <div className="flex justify-between text-gray-600">
            <span>Item:</span>
            <span className="font-bold text-[#352720]">{booking.item?.name}</span>
          </div>
          <div className="flex justify-between text-gray-600">
            <span>Renter:</span>
            <span className="font-semibold text-gray-800">
              {booking.renter?.full_name || 'Renter'}
            </span>
          </div>
          <div className="flex justify-between text-gray-600">
            <span>Booking Reference:</span>
            <span className="font-mono font-semibold text-[#9D4C29]">
              {booking.booking_reference}
            </span>
          </div>
        </div>

        {/* Success State */}
        {confirmed ? (
          <div className="my-6 text-center space-y-3">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
              <CheckCircle2 size={32} />
            </div>
            <div>
              <h4 className="text-base font-bold text-emerald-800">
                Pickup Confirmed!
              </h4>
              <p className="text-xs text-gray-600 mt-1">
                Item handover confirmed on <span className="font-semibold">{confirmedAt}</span>.
              </p>
              <p className="text-[11px] text-emerald-700 font-medium mt-1">
                Rental timer is now running. Rental in Progress!
              </p>
            </div>
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            {/* Error Message */}
            {error && (
              <div className="rounded-xl bg-rose-50 border border-rose-200 p-3 text-xs text-rose-800 flex items-start gap-2">
                <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                <div className="text-[11px] leading-relaxed">
                  <span className="font-bold block">Verification Error:</span>
                  {error}
                  {attemptsRemaining !== null && attemptsRemaining > 0 && (
                    <span className="block mt-0.5 font-semibold text-rose-900">
                      Attempts remaining: {attemptsRemaining} / 5
                    </span>
                  )}
                </div>
              </div>
            )}

            {!otpSent ? (
              /* State 1: Send OTP */
              <div className="space-y-4 pt-1">
                <div className="rounded-2xl bg-amber-50/70 border border-amber-200/60 p-3.5 text-xs text-amber-900 flex items-start gap-2.5">
                  <Smartphone size={18} className="text-[#D97745] shrink-0 mt-0.5" />
                  <div className="text-[11px] leading-relaxed">
                    <strong className="block font-semibold mb-0.5">
                      Handover Security Procedure:
                    </strong>
                    Click below to generate and send a 6-digit OTP to the renter's registered mobile number ({booking.renter_phone_masked || 'via SMS'}).
                    The renter must share this OTP with you in person to collect the item.
                  </div>
                </div>

                <div className="pt-2">
                  <button
                    type="button"
                    onClick={handleSendOtp}
                    disabled={loadingSend}
                    className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#D97745] px-4 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-[#B85D32] transition disabled:opacity-50 cursor-pointer"
                  >
                    {loadingSend ? (
                      <>
                        <RefreshCw size={14} className="animate-spin" />
                        Generating & Sending OTP...
                      </>
                    ) : (
                      <>
                        <Send size={14} />
                        Send Pickup OTP via SMS
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              /* State 2: OTP Sent, Awaiting Entry and Verification */
              <form onSubmit={handleVerifyOtp} className="space-y-4">
                {/* Sent Alert */}
                <div className="rounded-2xl bg-emerald-50 border border-emerald-200 p-3 text-xs text-emerald-900 flex items-start gap-2">
                  <CheckCircle2 size={16} className="text-emerald-600 shrink-0 mt-0.5" />
                  <div className="text-[11px] leading-relaxed">
                    <span className="font-semibold block">OTP Sent via SMS!</span>
                    A 6-digit OTP was sent to the renter's mobile ({maskedPhone}).
                    Valid for 10 minutes. Ask the renter for the OTP.
                  </div>
                </div>

                {/* OTP Input */}
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-[#352720]">
                    Enter 6-Digit Pickup OTP <span className="text-rose-600">*</span>
                  </label>
                  <div className="relative">
                    <KeyRound size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      maxLength={6}
                      autoFocus
                      value={otpInput}
                      onChange={(e) => setOtpInput(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      placeholder="• • • • • •"
                      className="w-full rounded-xl border border-gray-300 bg-white py-2.5 pl-10 pr-4 text-center font-mono text-lg font-bold tracking-widest text-[#352720] shadow-2xs focus:border-[#D97745] focus:outline-hidden focus:ring-2 focus:ring-[#D97745]/20 transition"
                    />
                  </div>
                </div>

                {/* Verification & Resend Buttons */}
                <div className="space-y-2 pt-1">
                  <button
                    type="submit"
                    disabled={otpInput.length !== 6 || loadingVerify}
                    className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#D97745] px-4 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-[#B85D32] transition disabled:opacity-50 cursor-pointer"
                  >
                    {loadingVerify ? (
                      <>
                        <RefreshCw size={14} className="animate-spin" />
                        Verifying OTP...
                      </>
                    ) : (
                      <>
                        <ShieldCheck size={14} />
                        Verify OTP & Confirm Pickup
                      </>
                    )}
                  </button>

                  <div className="flex items-center justify-between text-xs text-gray-500 pt-1">
                    <span className="flex items-center gap-1 text-[11px]">
                      <Clock size={12} className="text-gray-400" />
                      Expires in 10 mins
                    </span>

                    {cooldown > 0 ? (
                      <span className="text-[11px] text-gray-400 font-medium">
                        Resend available in {cooldown}s
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={handleSendOtp}
                        disabled={loadingSend || loadingVerify}
                        className="text-[11px] font-bold text-[#D97745] hover:underline cursor-pointer disabled:opacity-50"
                      >
                        {loadingSend ? 'Sending...' : 'Resend OTP'}
                      </button>
                    )}
                  </div>
                </div>
              </form>
            )}
          </div>
        )}

        {/* Footer Note */}
        <div className="mt-5 border-t border-orange-50 pt-3 text-center">
          <p className="text-[10px] text-gray-400">
            RentBee Handover Security • Rental timer begins immediately upon OTP confirmation.
          </p>
        </div>
      </div>
    </div>
  )
}
