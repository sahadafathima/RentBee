import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import { getBookingDetails, reportBookingProblem } from '../services/api'
import {
  ChevronRight,
  ArrowLeft,
  AlertCircle,
  Calendar,
  User,
  Package,
  Send,
  CheckCircle2,
} from 'lucide-react'

export default function ReportProblem() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [booking, setBooking] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [validationError, setValidationError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

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

  const handleSubmit = async (e) => {
    e.preventDefault()
    setValidationError('')

    const trimmed = description.trim()
    if (!trimmed) {
      setValidationError('Please provide a description of the issue.')
      return
    }

    setSubmitting(true)
    try {
      await reportBookingProblem(id, trimmed)
      setSuccessMessage(
        'Your report has been submitted successfully. The item owner and platform support have been notified.'
      )
      setTimeout(() => {
        navigate(`/bookings/${id}`)
      }, 2500)
    } catch (err) {
      setValidationError(err.message || 'Failed to submit problem report.')
    } finally {
      setSubmitting(false)
    }
  }

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
                <Link to="/bookings" className="hover:text-[#D97745] transition">
                  My Bookings
                </Link>
              </li>
              <li>
                <ChevronRight size={13} className="text-gray-400" />
              </li>
              {booking && (
                <>
                  <li>
                    <Link to={`/bookings/${booking.id}`} className="hover:text-[#D97745] transition">
                      {booking.booking_reference}
                    </Link>
                  </li>
                  <li>
                    <ChevronRight size={13} className="text-gray-400" />
                  </li>
                </>
              )}
              <li className="font-semibold text-[#352720]">Report Problem</li>
            </ol>
          </nav>

          {/* Form Container */}
          <div className="rounded-3xl border border-orange-100 bg-white p-6 sm:p-8 shadow-xs">
            
            {/* Header */}
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#D97745]">
                <AlertCircle size={15} />
                <span>Support & Mediation</span>
              </div>
              <h1 className="mt-1 text-2xl font-black text-[#352720] sm:text-3xl">
                Report the Problem
              </h1>
              <p className="mt-1 text-xs text-gray-500 sm:text-sm">
                Having an issue with your rental? Tell us what happened so we can help you resolve it.
              </p>
            </div>

            {loading ? (
              <div className="mt-6 space-y-4 animate-pulse">
                <div className="h-24 bg-orange-100/50 rounded-2xl" />
                <div className="h-32 bg-orange-100/30 rounded-2xl" />
              </div>
            ) : error ? (
              <div className="mt-6 rounded-2xl bg-rose-50 border border-rose-200 p-4 text-xs text-rose-800">
                {error}
              </div>
            ) : booking ? (
              <div className="mt-6 space-y-6">
                
                {/* Summary Box */}
                <div className="rounded-2xl bg-[#FFF9F5] border border-orange-100 p-4 flex flex-col sm:flex-row items-start sm:items-center gap-4">
                  <div className="h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-white border border-orange-100">
                    {booking.item?.primary_image_url ? (
                      <img
                        src={booking.item.primary_image_url}
                        alt={booking.item.name}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <div className="flex h-full w-full items-center justify-center text-orange-300">
                        <Package size={24} />
                      </div>
                    )}
                  </div>

                  <div className="flex-1 min-w-0 text-xs">
                    <p className="font-mono text-gray-400 font-medium">
                      {booking.booking_reference}
                    </p>
                    <h3 className="font-bold text-[#352720] text-sm truncate">
                      {booking.item?.name}
                    </h3>
                    <div className="mt-1 flex flex-wrap items-center gap-3 text-gray-500">
                      <span className="flex items-center gap-1">
                        <User size={13} className="text-[#D97745]" />
                        Owner: <strong className="text-[#49362D]">{booking.owner?.full_name}</strong>
                      </span>
                      <span className="flex items-center gap-1">
                        <Calendar size={13} className="text-[#D97745]" />
                        {booking.start_date} → {booking.end_date}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Success Notification */}
                {successMessage && (
                  <div className="rounded-2xl bg-emerald-50 border border-emerald-200 p-4 text-xs font-semibold text-emerald-800 flex items-start gap-2">
                    <CheckCircle2 size={16} className="text-emerald-600 shrink-0 mt-0.5" />
                    <div>
                      <p>{successMessage}</p>
                      <p className="mt-1 font-normal text-emerald-700">
                        Redirecting back to booking details...
                      </p>
                    </div>
                  </div>
                )}

                {/* Form */}
                {!successMessage && (
                  <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                      <label
                        htmlFor="problem-description"
                        className="block text-xs font-bold text-[#352720] mb-1.5"
                      >
                        Describe the problem: <span className="text-rose-500">*</span>
                      </label>
                      <textarea
                        id="problem-description"
                        rows={5}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Describe the problem you experienced with this rental (e.g. equipment malfunction, missing accessory, unexpected defect)..."
                        className="w-full rounded-2xl border border-orange-200 bg-white p-3.5 text-xs sm:text-sm text-[#352720] placeholder-gray-400 focus:border-[#D97745] focus:outline-none focus:ring-2 focus:ring-orange-200/50"
                      />
                      {validationError && (
                        <p className="mt-1.5 text-xs text-rose-600 font-medium">
                          {validationError}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                      <Link
                        to={`/bookings/${id}`}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-orange-200 bg-white px-4 py-2.5 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition"
                      >
                        <ArrowLeft size={14} /> Back
                      </Link>

                      <button
                        type="submit"
                        disabled={submitting}
                        className="inline-flex items-center gap-2 rounded-xl bg-[#D97745] px-5 py-2.5 text-xs font-semibold text-white hover:bg-[#B85D32] transition disabled:opacity-50 cursor-pointer"
                      >
                        <Send size={14} />
                        {submitting ? 'Submitting Report...' : 'Report an Issue'}
                      </button>
                    </div>
                  </form>
                )}

              </div>
            ) : null}

          </div>
        </main>
      </div>

      <Footer />
    </div>
  )
}

