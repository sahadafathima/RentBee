import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Navbar from '../Components/Navbar'
import Footer from '../Components/Footer'
import {
  getHostBookings,
  getHostReports,
  ownerApproveBooking,
  ownerRejectBooking,
  confirmPickup,
  confirmReturn,
} from '../services/api'
import {
  Inbox,
  CheckCircle2,
  Clock,
  Calendar,
  Package,
  User,
  ShieldCheck,
  Check,
  X,
  Phone,
} from 'lucide-react'
import { formatKolkataDateTime, calculateReturnCountdown } from '../utils/dateUtils'

export default function HostHub() {
  const [activeTab, setActiveTab] = useState('incoming')
  const [bookings, setBookings] = useState([])
  const [reports, setReports] = useState([])
  const [counts, setCounts] = useState({ all: 0, incoming: 0, active: 0, completed: 0 })
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [toastMessage, setToastMessage] = useState('')

  // Reject modal
  const [rejectingBooking, setRejectingBooking] = useState(null)
  const [rejectReason, setRejectReason] = useState('')

  const reloadData = () => {
    setLoading(true)
    if (activeTab === 'reports') {
      getHostReports()
        .then((reportData) => {
          setReports(reportData || [])
          setLoading(false)
        })
        .catch(() => setLoading(false))
    } else {
      getHostBookings({ tab: activeTab })
        .then((data) => {
          setBookings(data.results || [])
          setCounts(data.counts || { all: 0, incoming: 0, active: 0, completed: 0 })
          setLoading(false)
        })
        .catch(() => setLoading(false))
    }
  }

  useEffect(() => {
    let isCurrent = true
    if (activeTab === 'reports') {
      getHostReports()
        .then((reportData) => {
          if (isCurrent) {
            setReports(reportData || [])
            setLoading(false)
          }
        })
        .catch((err) => {
          if (isCurrent) {
            console.error('Failed to load host hub reports:', err)
            setLoading(false)
          }
        })
    } else {
      getHostBookings({ tab: activeTab })
        .then((data) => {
          if (isCurrent) {
            setBookings(data.results || [])
            setCounts(data.counts || { all: 0, incoming: 0, active: 0, completed: 0 })
            setLoading(false)
          }
        })
        .catch((err) => {
          if (isCurrent) {
            console.error('Failed to load host hub bookings:', err)
            setLoading(false)
          }
        })
    }

    return () => {
      isCurrent = false
    }
  }, [activeTab])

  const showToast = (msg) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(''), 4000)
  }

  const handleApprove = async (id) => {
    setActionLoading(true)
    try {
      await ownerApproveBooking(id)
      showToast('Booking request approved! Now waiting for payment & pickup.')
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to approve booking.')
    } finally {
      setActionLoading(false)
    }
  }

  const handleRejectConfirm = async () => {
    if (!rejectingBooking) return
    setActionLoading(true)
    try {
      await ownerRejectBooking(rejectingBooking.id, rejectReason)
      setRejectingBooking(null)
      setRejectReason('')
      showToast('Booking request declined.')
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to decline booking.')
    } finally {
      setActionLoading(false)
    }
  }

  const handlePickup = async (id) => {
    setActionLoading(true)
    try {
      await confirmPickup(id)
      showToast('Item handover confirmed! Rental is now in progress.')
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to confirm pickup.')
    } finally {
      setActionLoading(false)
    }
  }

  const handleReturn = async (id) => {
    if (!window.confirm('Confirm that the rental item has been returned safely in good condition?')) {
      return
    }
    setActionLoading(true)
    try {
      await confirmReturn(id)
      showToast('Rental return confirmed and marked completed!')
      reloadData()
    } catch (err) {
      alert(err.message || 'Failed to confirm return.')
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#FFFCF9] flex flex-col justify-between">
      <div>
        <Navbar />

        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          
          {/* Toast Notification */}
          {toastMessage && (
            <div className="mb-6 flex items-center gap-2 rounded-2xl bg-emerald-50 border border-emerald-200 p-4 text-xs font-semibold text-emerald-800 animate-in fade-in">
              <CheckCircle2 size={16} className="text-emerald-600" />
              <span>{toastMessage}</span>
            </div>
          )}

          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-black text-[#352720] sm:text-3xl">
              Host Hub
            </h1>
            <p className="mt-1 text-xs text-gray-500 sm:text-sm max-w-2xl">
              Manage incoming rental requests, coordinate pickup handovers, confirm returns, and review renter issues.
            </p>
          </div>

          {/* Navigation Tabs */}
          <div className="flex flex-wrap gap-2 border-b border-orange-100 pb-3 mb-6">
            <button
              type="button"
              onClick={() => setActiveTab('incoming')}
              className={`rounded-full px-4 py-2 text-xs font-bold transition flex items-center gap-2 cursor-pointer ${
                activeTab === 'incoming'
                  ? 'bg-[#9D4C29] text-white shadow-xs'
                  : 'bg-white border border-orange-200 text-[#49362D] hover:bg-orange-50'
              }`}
            >
              <span>Incoming Requests</span>
              <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                {counts.incoming}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('active')}
              className={`rounded-full px-4 py-2 text-xs font-bold transition flex items-center gap-2 cursor-pointer ${
                activeTab === 'active'
                  ? 'bg-[#D97745] text-white shadow-xs'
                  : 'bg-white border border-orange-200 text-[#49362D] hover:bg-orange-50'
              }`}
            >
              <span>Active Rentals</span>
              <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                {counts.active}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('completed')}
              className={`rounded-full px-4 py-2 text-xs font-bold transition flex items-center gap-2 cursor-pointer ${
                activeTab === 'completed'
                  ? 'bg-emerald-700 text-white shadow-xs'
                  : 'bg-white border border-orange-200 text-[#49362D] hover:bg-orange-50'
              }`}
            >
              <span>Completed</span>
              <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px]">
                {counts.completed}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('reports')}
              className={`rounded-full px-4 py-2 text-xs font-bold transition flex items-center gap-2 cursor-pointer ${
                activeTab === 'reports'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'bg-white border border-orange-200 text-[#49362D] hover:bg-orange-50'
              }`}
            >
              <span>Reported Issues</span>
            </button>
          </div>

          {/* Content Area */}
          {loading ? (
            <div className="space-y-4">
              {[1, 2].map((n) => (
                <div
                  key={n}
                  className="h-36 rounded-3xl bg-white border border-orange-100 p-6 animate-pulse"
                />
              ))}
            </div>
          ) : activeTab === 'reports' ? (
            /* Reported Issues Tab */
            reports.length > 0 ? (
              <div className="space-y-4">
                {reports.map((report) => (
                  <div
                    key={report.id}
                    className="rounded-3xl border border-rose-100 bg-white p-5 sm:p-6 shadow-xs"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-rose-100 px-2.5 py-0.5 text-[10px] font-bold text-rose-800 uppercase">
                          {report.status}
                        </span>
                        <span className="text-xs text-gray-400">
                          Filed on {new Date(report.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <Link
                        to={`/bookings/${report.booking}`}
                        className="text-xs font-semibold text-[#D97745] hover:underline"
                      >
                        View Booking
                      </Link>
                    </div>

                    <div className="mt-3 text-xs">
                      <p className="text-gray-500">
                        Renter: <strong className="text-[#352720]">{report.renter_name}</strong>
                      </p>
                      <div className="mt-2 rounded-2xl bg-rose-50/50 border border-rose-100 p-3.5 text-[#352720]">
                        <strong className="block text-xs font-bold text-rose-900 mb-1">
                          Issue Description:
                        </strong>
                        <p className="leading-relaxed">{report.description}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-3xl border border-orange-100 bg-white p-12 text-center shadow-xs">
                <ShieldCheck size={36} className="mx-auto text-emerald-600 mb-3" />
                <h3 className="text-base font-bold text-[#352720]">No Reported Issues</h3>
                <p className="mt-1 text-xs text-gray-500">
                  Great job! You have no unresolved problems or complaints for your rental items.
                </p>
              </div>
            )
          ) : (
            /* Bookings Tabs (Incoming / Active / Completed) */
            bookings.length > 0 ? (
              <div className="space-y-4">
                {bookings.map((b) => (
                  <div
                    key={b.id}
                    className="rounded-3xl border border-orange-100 bg-white p-5 sm:p-6 shadow-xs"
                  >
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                      <div className="flex flex-col sm:flex-row gap-4">
                        <div className="h-24 w-24 shrink-0 overflow-hidden rounded-2xl bg-orange-50 border border-orange-100">
                          {b.item?.primary_image_url ? (
                            <img
                              src={b.item.primary_image_url}
                              alt={b.item.name}
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <div className="flex h-full w-full items-center justify-center text-orange-300">
                              <Package size={30} />
                            </div>
                          )}
                        </div>

                        <div className="space-y-1 text-xs">
                          <span className="font-mono text-gray-400 font-medium">
                            {b.booking_reference}
                          </span>
                          <h3 className="text-base font-bold text-[#352720]">
                            {b.item?.name}
                          </h3>

                          <div className="flex flex-wrap items-center gap-3 text-gray-600 pt-1">
                            <span className="flex items-center gap-1">
                              <User size={13} className="text-[#D97745]" />
                              Renter: <strong className="text-[#49362D]">{b.renter?.full_name}</strong>
                            </span>
                            {b.renter?.phone_number && (
                              <a
                                href={`tel:${b.renter.phone_number}`}
                                className="flex items-center gap-1 text-emerald-700 font-medium"
                              >
                                <Phone size={12} /> {b.renter.phone_number}
                              </a>
                            )}
                          </div>

                          <div className="flex flex-wrap items-center gap-3 text-gray-500 pt-1">
                            <span className="flex items-center gap-1">
                              <Calendar size={13} className="text-[#D97745]" />
                              {b.start_date} → {b.end_date} ({b.duration_days} {b.duration_days === 1 ? 'day' : 'days'})
                            </span>
                            <span className="font-bold text-[#9D4C29]">
                              Total: ₹{b.total_amount}
                            </span>
                          </div>

                          {/* Rental in Progress: Exact Return Deadline & Countdown */}
                          {b.status === 'rental_in_progress' && b.return_deadline && (
                            <div className="mt-2 rounded-xl bg-[#FFF9F5] border border-orange-200/80 p-2.5 text-xs text-[#352720] space-y-1">
                              <div className="flex items-center gap-1.5 font-bold text-[#9D4C29]">
                                <Clock size={13} />
                                <span>Return Deadline: {b.return_deadline_display || formatKolkataDateTime(b.return_deadline)}</span>
                              </div>
                              <div className="text-[11px] text-gray-500 flex flex-wrap items-center justify-between gap-1">
                                <span>Picked up: {b.picked_up_at_display || formatKolkataDateTime(b.picked_up_at)}</span>
                                <span className={`font-semibold ${calculateReturnCountdown(b.return_deadline).isOverdue ? 'text-rose-600' : 'text-emerald-700'}`}>
                                  {calculateReturnCountdown(b.return_deadline).text}
                                </span>
                              </div>
                            </div>
                          )}

                          {/* Completed: Return confirmation timestamp */}
                          {b.status === 'completed' && (b.returned_at || b.returned_at_display) && (
                            <div className="mt-1 text-[11px] text-gray-500">
                              Returned: {b.returned_at_display || formatKolkataDateTime(b.returned_at)}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Status and Action Buttons */}
                      <div className="flex flex-col items-start sm:items-end justify-between gap-3 border-t border-orange-50 pt-3 sm:border-0 sm:pt-0">
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                            b.status === 'pending_approval'
                              ? 'bg-amber-100 text-amber-800'
                              : b.status === 'waiting_for_pickup'
                              ? 'bg-orange-100 text-[#9D4C29]'
                              : b.status === 'rental_in_progress'
                              ? 'bg-blue-100 text-blue-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {b.status_display}
                        </span>

                        <div className="flex flex-wrap gap-2">
                          
                          {/* Pending Approval: Approve or Decline */}
                          {b.status === 'pending_approval' && (
                            <>
                              <button
                                type="button"
                                onClick={() => handleApprove(b.id)}
                                disabled={actionLoading}
                                className="inline-flex items-center gap-1 rounded-xl bg-emerald-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 transition cursor-pointer"
                              >
                                <Check size={13} /> Approve
                              </button>
                              <button
                                type="button"
                                onClick={() => setRejectingBooking(b)}
                                disabled={actionLoading}
                                className="inline-flex items-center gap-1 rounded-xl border border-rose-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 transition cursor-pointer"
                              >
                                <X size={13} /> Decline
                              </button>
                            </>
                          )}

                          {/* Waiting for Pickup: Confirm Pickup */}
                          {b.status === 'waiting_for_pickup' && (
                            <div className="flex flex-col items-end gap-1">
                              {b.payment_status === 'paid' ? (
                                <button
                                  type="button"
                                  onClick={() => handlePickup(b.id)}
                                  disabled={actionLoading}
                                  className="rounded-xl bg-[#D97745] px-4 py-1.5 text-xs font-semibold text-white hover:bg-[#B85D32] transition cursor-pointer"
                                >
                                  Confirm Pickup
                                </button>
                              ) : (
                                <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-800 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-xl">
                                  <Clock size={12} />
                                  <span>Awaiting Payment Verification</span>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Rental in Progress: Confirm Return */}
                          {b.status === 'rental_in_progress' && (
                            <button
                              type="button"
                              onClick={() => handleReturn(b.id)}
                              disabled={actionLoading}
                              className="rounded-xl bg-emerald-700 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800 transition cursor-pointer"
                            >
                              Confirm Return
                            </button>
                          )}

                          <Link
                            to={`/bookings/${b.id}`}
                            className="rounded-xl border border-orange-200 bg-white px-3 py-1.5 text-xs font-semibold text-[#49362D] hover:bg-orange-50 transition"
                          >
                            Details
                          </Link>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-3xl border border-orange-100 bg-white p-12 text-center shadow-xs">
                <Inbox size={36} className="mx-auto text-orange-300 mb-3" />
                <h3 className="text-base font-bold text-[#352720]">No Bookings Found</h3>
                <p className="mt-1 text-xs text-gray-500">
                  There are no {activeTab} bookings for your equipment at this moment.
                </p>
              </div>
            )
          )}

        </main>
      </div>

      <Footer />

      {/* Decline Reason Modal */}
      {rejectingBooking && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl border border-orange-100">
            <h3 className="text-base font-bold text-[#352720]">Decline Booking Request</h3>
            <p className="text-xs text-gray-500 mt-1">
              For {rejectingBooking.item?.name} requested by {rejectingBooking.renter?.full_name}.
            </p>

            <div className="mt-4">
              <label className="block text-xs font-semibold text-[#352720] mb-1">
                Reason for declining (optional):
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="e.g. Equipment undergoing maintenance, dates not convenient..."
                rows={2}
                className="w-full rounded-xl border border-orange-200 p-2.5 text-xs text-[#352720] focus:border-[#D97745] focus:outline-none"
              />
            </div>

            <div className="mt-6 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={() => {
                  setRejectingBooking(null)
                  setRejectReason('')
                }}
                className="rounded-xl border border-orange-200 px-4 py-2 text-xs font-semibold text-gray-600 hover:bg-orange-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRejectConfirm}
                disabled={actionLoading}
                className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700"
              >
                {actionLoading ? 'Declining...' : 'Decline Request'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
